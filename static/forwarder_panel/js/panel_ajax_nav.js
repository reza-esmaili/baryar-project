// static/forwarder_panel/js/panel_ajax_nav.js
// ناوبری بدون رفرش کامل صفحه برای سایدبار پنل فورواردر (شبیه pjax).
// با کلیک روی آیتم‌های سایدبار، صفحه مقصد به‌صورت کامل از سرور واکشی می‌شود،
// اما فقط محتوای اصلی (#panelMainContent) و اسکریپت‌های اختصاصی صفحه
// (#panelPageScripts) جایگزین می‌شوند؛ سایدبار و اسکریپت‌های پایه دوباره اجرا نمی‌شوند.
(function () {
    'use strict';

    var mainSelector = '#panelMainContent';
    var pageScriptsSelector = '#panelPageScripts';
    var activeController = null;

    // شماره‌ی نسل ناوبری؛ در panelReady (panel_chrome.js) برای رد کردن
    // اجرای دیرهنگام اسکریپت‌های متعلق به صفحه‌ی رهاشده استفاده می‌شود.
    window.__panelEpoch = window.__panelEpoch || 0;

    function sameOrigin(url) {
        try {
            return new URL(url, window.location.href).origin === window.location.origin;
        } catch (e) {
            return false;
        }
    }

    function pathOf(url) {
        try {
            return new URL(url, window.location.href).pathname;
        } catch (e) {
            return '';
        }
    }

    function showLoading() {
        var bar = document.getElementById('panelLoadingBar');
        var main = document.querySelector(mainSelector);
        if (bar) { bar.classList.remove('done'); bar.classList.add('loading'); }
        if (main) main.classList.add('is-loading');
    }

    function hideLoading() {
        var bar = document.getElementById('panelLoadingBar');
        var main = document.querySelector(mainSelector);
        if (bar) {
            bar.classList.remove('loading');
            bar.classList.add('done');
            setTimeout(function () { bar.classList.remove('done'); }, 300);
        }
        if (main) main.classList.remove('is-loading');
    }

    // اسکریپت‌های داخل یک کانتینر را با نسخه‌ی تازه جایگزین می‌کند تا واقعا اجرا شوند
    // (innerHTML اسکریپت را در DOM قرار می‌دهد ولی هرگز اجرایش نمی‌کند).
    function reviveScripts(container) {
        var oldScripts = Array.prototype.slice.call(container.querySelectorAll('script'));
        var loadPromises = [];
        oldScripts.forEach(function (oldScript) {
            var newScript = document.createElement('script');
            for (var i = 0; i < oldScript.attributes.length; i++) {
                var attr = oldScript.attributes[i];
                newScript.setAttribute(attr.name, attr.value);
            }
            newScript.dataset.panelEpoch = String(window.__panelEpoch);
            if (oldScript.src) {
                newScript.async = false; // حفظ ترتیب اجرای مطابق سند اصلی
                loadPromises.push(new Promise(function (resolve) {
                    newScript.addEventListener('load', resolve, { once: true });
                    newScript.addEventListener('error', resolve, { once: true });
                }));
            } else {
                newScript.textContent = oldScript.textContent;
            }
            oldScript.parentNode.replaceChild(newScript, oldScript);
        });
        return Promise.all(loadPromises);
    }

    // بخش {% block extra_css %} هر صفحه (چه لینک فایل CSS و چه <style> اینلاین)
    // بین دو کامنت مارکر در <head> پایه (base.html) قرار دارد. چون هر صفحه ممکن
    // است هرکدام از این دو روش را استفاده کند، به‌جای merge کردن فقط <link>ها،
    // کل محدوده‌ی بین مارکرها با محتوای صفحه‌ی جدید جایگزین می‌شود.
    function findMarkerRange(headEl) {
        var start = null, end = null;
        var walker = document.createTreeWalker(headEl, NodeFilter.SHOW_COMMENT);
        var node;
        while ((node = walker.nextNode())) {
            var text = node.nodeValue.trim();
            if (text === 'panel-page-css:start') start = node;
            else if (text === 'panel-page-css:end' && start) { end = node; break; }
        }
        return { start: start, end: end };
    }

    function replacePageHeadAssets(doc) {
        var currentRange = findMarkerRange(document.head);
        var newRange = findMarkerRange(doc.head);
        if (!currentRange.start || !currentRange.end || !newRange.start || !newRange.end) {
            return Promise.resolve();
        }

        // حذف style/link اختصاصی صفحه‌ی قبلی
        var node = currentRange.start.nextSibling;
        while (node && node !== currentRange.end) {
            var next = node.nextSibling;
            node.remove();
            node = next;
        }

        // جمع‌آوری گره‌های صفحه‌ی جدید پیش از دستکاری DOM جاری
        var toInsert = [];
        var n = newRange.start.nextSibling;
        while (n && n !== newRange.end) {
            toInsert.push(n);
            n = n.nextSibling;
        }

        var loadPromises = [];
        toInsert.forEach(function (item) {
            if (item.nodeType !== 1) return; // فقط element (متن/کامنت رد شود)
            if (item.tagName === 'SCRIPT') {
                var s = document.createElement('script');
                for (var i = 0; i < item.attributes.length; i++) {
                    s.setAttribute(item.attributes[i].name, item.attributes[i].value);
                }
                if (item.src) {
                    loadPromises.push(new Promise(function (resolve) {
                        s.addEventListener('load', resolve, { once: true });
                        s.addEventListener('error', resolve, { once: true });
                    }));
                } else {
                    s.textContent = item.textContent;
                }
                currentRange.end.parentNode.insertBefore(s, currentRange.end);
            } else {
                // <link>/<style>: import و درج ساده کافی است تا اعمال شود
                currentRange.end.parentNode.insertBefore(document.importNode(item, true), currentRange.end);
            }
        });

        return Promise.all(loadPromises);
    }

    function updateActiveNav() {
        var links = document.querySelectorAll('.sidebar-nav a[href]');
        if (!links.length) return;
        var currentPath = window.location.pathname;
        // لینک داشبورد همیشه اولین آیتم سایدبار و "ریشه" پنل است؛ چون بعضی
        // زیرمسیرها (مثل پشتیبانی) واقعا زیر /panel/ نیستند، مسیر ریشه را
        // به‌جای هارد-کد کردن /panel/ از خودِ سایدبار می‌خوانیم.
        var rootPath = pathOf(links[0].href);
        links.forEach(function (a) {
            var linkPath = pathOf(a.href);
            var isActive = linkPath === rootPath
                ? currentPath === rootPath
                : currentPath.indexOf(linkPath) === 0;
            a.classList.toggle('active', isActive);
        });
    }

    function renderPage(html, finalUrl, push) {
        var doc = new DOMParser().parseFromString(html, 'text/html');
        var newMain = doc.querySelector(mainSelector);
        var currentMain = document.querySelector(mainSelector);
        var newPageScripts = doc.querySelector(pageScriptsSelector);
        var currentPageScripts = document.querySelector(pageScriptsSelector);

        if (!newMain || !currentMain) {
            window.location.href = finalUrl;
            return Promise.resolve();
        }

        var headAssetsDone = replacePageHeadAssets(doc);
        if (doc.title) document.title = doc.title;

        currentMain.innerHTML = newMain.innerHTML;
        var mainScriptsDone = reviveScripts(currentMain);

        var pageScriptsDone = Promise.resolve();
        if (newPageScripts && currentPageScripts) {
            currentPageScripts.innerHTML = newPageScripts.innerHTML;
            pageScriptsDone = reviveScripts(currentPageScripts);
        }

        if (push) {
            history.pushState({ ajaxNav: true }, '', finalUrl);
        } else {
            history.replaceState({ ajaxNav: true }, '', finalUrl);
        }

        updateActiveNav();
        window.scrollTo(0, 0);

        // توجه: رویداد DOMContentLoaded دوباره dispatch نمی‌شود، چون Listenerهای
        // صفحات قبلی هرگز پاک نمی‌شوند و دوباره روی DOM جدید اجرا می‌شدند (خطای
        // null). به‌جایش هر اسکریپت با تابع سراسری panelReady (در panel_chrome.js)
        // بلافاصله بعد از revive شدن، خودش را اجرا می‌کند.
        return Promise.all([mainScriptsDone, pageScriptsDone, headAssetsDone]).then(function () {
            document.dispatchEvent(new CustomEvent('panel:content-loaded'));
        });
    }

    function navigateTo(url, push) {
        if (activeController) activeController.abort();
        var controller = new AbortController();
        activeController = controller;
        window.__panelEpoch++;

        showLoading();

        // توجه: هدر X-Requested-With عمداً ارسال نمی‌شود؛ چند ویوی دیگر پنل
        // (مثلاً support.views.ticket_list) همین هدر را برای تشخیص «فقط
        // ردیف‌های جدول را به‌صورت JSON بده» استفاده می‌کنند و اگر بفرستیمش
        // به‌جای صفحه‌ی کامل HTML یک JSON جزئی برمی‌گردد.
        fetch(url, {
            credentials: 'same-origin',
            signal: controller.signal
        }).then(function (response) {
            if (!response.ok) {
                window.location.href = response.url || url;
                return null;
            }
            return response.text().then(function (html) {
                return { html: html, finalUrl: response.url || url };
            });
            // اعتبارسنجی این‌که پاسخ واقعا یک صفحه‌ی پنل است (وجود #panelMainContent)
            // در renderPage انجام می‌شود؛ چون بعضی مسیرهای معتبر پنل (مثل پشتیبانی)
            // زیر /panel/ نیستند و بررسی بر اساس پیشوند URL نادرست بود.
        }).then(function (result) {
            if (!result) return null;
            return renderPage(result.html, result.finalUrl, push);
        }).catch(function (err) {
            if (err && err.name === 'AbortError') return;
            window.location.href = url;
        }).finally(function () {
            if (activeController === controller) {
                hideLoading();
                activeController = null;
            }
        });
    }

    document.addEventListener('click', function (e) {
        var link = e.target && e.target.closest ? e.target.closest('.sidebar-nav a[href]') : null;
        if (!link) return;
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        if (link.target && link.target !== '_self') return;
        if (link.hasAttribute('data-no-ajax')) return;
        if (!sameOrigin(link.href)) return;

        var url = link.href;
        if (url === window.location.href) { e.preventDefault(); return; }

        e.preventDefault();
        navigateTo(url, true);
    });

    window.addEventListener('popstate', function () {
        navigateTo(window.location.href, false);
    });

    updateActiveNav();
})();
