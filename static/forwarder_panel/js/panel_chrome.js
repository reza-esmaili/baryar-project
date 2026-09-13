// static/forwarder_panel/js/panel_chrome.js
// رفتار ثابت پوسته پنل فورواردر: تاگل سایدبار، اعلان‌ها و مودال خروج.
// این فایل خارج از سایدبار/main-content قرار دارد و در ناوبری AJAX دوباره بارگذاری نمی‌شود.
(function () {
    'use strict';

    // توجه: window.panelReady و window.__panelEpoch در <head> پایه (base.html)
    // به‌صورت inline تعریف شده‌اند، نه اینجا — چون بعضی صفحات (مثلا
    // order_list.html) اسکریپتشان را داخل خودِ content قرار می‌دهند که در DOM
    // زودتر از این فایل (که در پایین body لود می‌شود) قرار می‌گیرد؛ اگر
    // panelReady اینجا تعریف می‌شد، روی چنان صفحاتی هنوز تعریف نشده بود.

    function csrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : '';
    }

    function initSidebarToggle() {
        var sidebar = document.getElementById('mainSidebar');
        var btn = document.getElementById('sidebarToggle');
        if (!sidebar) return;
        if (localStorage.getItem('sidebarCollapsed') === '1') sidebar.classList.add('collapsed');
        if (btn) {
            btn.addEventListener('click', function () {
                sidebar.classList.toggle('collapsed');
                localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed') ? '1' : '0');
            });
        }
    }

    function initNotifications() {
        var wrap = document.getElementById('fwNotifWrap');
        if (!wrap) return;

        var NOTIF_URL = wrap.getAttribute('data-notif-url');
        var MARK_URL  = wrap.getAttribute('data-mark-url');

        var fwBtn     = document.getElementById('fwNotifBtn');
        var fwBadge   = document.getElementById('fwNotifBadge');
        var fwDrop    = document.getElementById('fwNotifDropdown');
        var fwList    = document.getElementById('fwNotifList');
        var fwMarkBtn = document.getElementById('fwMarkReadBtn');
        var fwIcon    = fwBtn ? fwBtn.querySelector('i') : null;
        var fwCount   = 0;

        function fetchFwNotifs() {
            fetch(NOTIF_URL, { credentials: 'same-origin' })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    var count = data.count || 0;
                    var items = data.items || [];
                    fwBadge.textContent = count > 99 ? '99+' : count;
                    fwBadge.style.display = count > 0 ? 'flex' : 'none';
                    if (count > 0 && count !== fwCount && fwIcon) {
                        fwIcon.classList.add('ringing');
                        setTimeout(function () { fwIcon.classList.remove('ringing'); }, 3000);
                    }
                    fwCount = count;
                    if (items.length === 0) {
                        fwList.innerHTML = '<div class="fw-notif-empty">هیچ اعلان جدیدی ندارید</div>';
                    } else {
                        fwList.innerHTML = items.map(function (n) {
                            return '<a class="fw-notif-item" href="' + n.url + '">'
                                + '<div class="fw-notif-title">' + n.title + '</div>'
                                + '<div class="fw-notif-sub">' + n.subtitle + ' &bull; ' + n.created_at + '</div>'
                                + '</a>';
                        }).join('');
                    }
                }).catch(function () {});
        }

        function positionFwDrop() {
            var rect = fwBtn.getBoundingClientRect();
            fwDrop.style.top  = (rect.bottom + 6) + 'px';
            fwDrop.style.right = (window.innerWidth - rect.right) + 'px';
        }

        if (fwBtn) {
            fwBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                var isOpen = fwDrop.classList.toggle('open');
                if (isOpen) { positionFwDrop(); fetchFwNotifs(); }
            });
        }
        document.addEventListener('click', function (e) {
            if (fwBtn && !fwBtn.closest('#fwNotifWrap').contains(e.target)) {
                fwDrop && fwDrop.classList.remove('open');
            }
        });
        if (fwMarkBtn) {
            fwMarkBtn.addEventListener('click', function () {
                fetch(MARK_URL, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrfToken() } })
                    .then(function () {
                        fwBadge.style.display = 'none';
                        fwCount = 0;
                        fwList.innerHTML = '<div class="fw-notif-empty">هیچ اعلان جدیدی ندارید</div>';
                        fwDrop.classList.remove('open');
                    });
            });
        }
        fetchFwNotifs();
        setInterval(fetchFwNotifs, 60000);
    }

    function initLogoutModal() {
        var modal = document.getElementById('fwLogoutModal');
        if (!modal) return;
        window.openFwLogoutModal = function () { modal.style.display = 'flex'; };
        window.closeFwLogoutModal = function () { modal.style.display = 'none'; };
        modal.addEventListener('click', function (e) {
            if (e.target === modal) window.closeFwLogoutModal();
        });
    }

    initSidebarToggle();
    initNotifications();
    initLogoutModal();
})();
