$(document).ready(function () {

 
    $('.select2-multiple').select2({
        placeholder: "زیردسته‌های کالا را انتخاب کنید",
        allowClear: true,
        width: '100%',
        dir: "rtl"
    });
 
    // ── مدیریت تیک «برای فرد دیگری» ─────────────────────────────
    const $checkbox = $('#is_for_other_checkbox');
 
    // فیلدهای جدید: نام و نام خانوادگی مجزا
    const $firstName = $('#id_sender_first_name');
    const $lastName  = $('#id_sender_last_name');
    const $national  = $('#id_sender_national_id');
    const $phone     = $('#id_sender_phone');
    const $address   = $('#id_sender_address');
 
    const $user = $('#current_user_data');
 
    function restoreUserData() {
        // بازگرداندن اطلاعات از data attribute های کاربر
        $firstName.val($user.data('first-name'));
        $lastName.val($user.data('last-name'));
        $national.val($user.data('national-id'));
        $phone.val($user.data('phone'));
        if ($address.length) {
            $address.val($user.data('address'));
        }
    }
 
    function clearUserData() {
        // پاک کردن همه فیلدها برای ورود اطلاعات فرد دیگر
        $firstName.val('');
        $lastName.val('');
        $national.val('');
        $phone.val('');
        // آدرس را پاک نمی‌کنیم چون مربوط به مبدا است، نه فرستنده
    }
 
    if ($checkbox.length) {
        $checkbox.on('change', function () {
            if ($(this).is(':checked')) {
                clearUserData();
            } else {
                restoreUserData();
            }
        });
    }
 
    // ── باقی کد (submit, wizard, ...) بدون تغییر می‌ماند ─────────
    $('#complete-order-form').on('submit', function () {
        const btn = $('#submit-btn');
        btn.prop('disabled', true);
        btn.html(`
            <span class="spinner-border spinner-border-sm"></span>
            در حال ثبت سفارش...
        `);
    });

    // ---------------------------
    // Wizard / Step Navigation
    // ---------------------------
    const panels = document.querySelectorAll('.complete-step-panel');
    const indicators = document.querySelectorAll('.complete-step-item');

    const prevBtn = document.getElementById('complete-prev-btn');
    const nextBtn = document.getElementById('complete-next-btn');
    const submitBtn = document.getElementById('submit-btn');

    const form = document.getElementById('complete-order-form');

    let currentStep = 1;
    const totalSteps = panels.length || 5;

    function showStep(step) {
        panels.forEach(panel => {
            const panelStep = Number(panel.dataset.step);
            panel.classList.toggle('active', panelStep === step);
        });

        indicators.forEach(indicator => {
            const indicatorStep = Number(indicator.dataset.stepIndicator);
            indicator.classList.toggle('active', indicatorStep === step);
            indicator.classList.toggle('done', indicatorStep < step);
        });

        if (prevBtn) {
            prevBtn.style.display = step === 1 ? 'none' : 'inline-flex';
        }

        if (nextBtn) {
            nextBtn.style.display = step === totalSteps ? 'none' : 'inline-flex';
        }

        if (submitBtn) {
            submitBtn.style.display = step === totalSteps ? 'inline-flex' : 'none';
        }

        // const firstActivePanel = document.querySelector(`.complete-step-panel[data-step="${step}"]`);

        // if (firstActivePanel) {
        //     firstActivePanel.scrollIntoView({
        //         behavior: 'smooth',
        //         block: 'start'
        //     });
        // }

    }

    function getStepFields(step) {
        const activePanel = document.querySelector(`.complete-step-panel[data-step="${step}"]`);

        if (!activePanel) {
            return [];
        }

        return Array.from(activePanel.querySelectorAll('input, select, textarea')).filter(field => {
            return !field.disabled && field.type !== 'hidden';
        });
    }

    function clearFieldError(field) {
        field.classList.remove('field-error');

        const wrapper = field.closest('.form-group') || field.parentElement;
        if (!wrapper) {
            return;
        }

        const oldMessage = wrapper.querySelector('.client-error-message');
        if (oldMessage) {
            oldMessage.remove();
        }
    }

    function showFieldError(field, message) {
        field.classList.add('field-error');

        const wrapper = field.closest('.form-group') || field.parentElement;
        if (!wrapper) {
            return;
        }

        const oldMessage = wrapper.querySelector('.client-error-message');
        if (oldMessage) {
            oldMessage.remove();
        }

        const error = document.createElement('div');
        error.className = 'client-error-message';
        error.innerText = message;

        wrapper.appendChild(error);
    }

    function validateCurrentStep() {
        const fields = getStepFields(currentStep);
        let isValid = true;
        let firstInvalidField = null;

        fields.forEach(field => {
            clearFieldError(field);

            const isRequired = field.hasAttribute('required');
            if (!isRequired) {
                return;
            }

            let valueIsEmpty = false;
            if (field.tagName === 'SELECT') {
                if (field.multiple) {
                    valueIsEmpty = !Array.from(field.selectedOptions).length;
                } else {
                    valueIsEmpty = !field.value;
                }
            } else if (field.type === 'checkbox' || field.type === 'radio') {
                const sameNameFields = form.querySelectorAll(`[name="${field.name}"]`);
                valueIsEmpty = !Array.from(sameNameFields).some(item => item.checked);
            } else if (field.type === 'file') {
                valueIsEmpty = !field.files || field.files.length === 0;
            } else {
                valueIsEmpty = !field.value.trim();
            }


            if (valueIsEmpty) {
                isValid = false;

                if (!firstInvalidField) {
                    firstInvalidField = field;
                }

                showFieldError(field, 'تکمیل این فیلد الزامی است.');
            }
        });

        if (!isValid && firstInvalidField) {
            firstInvalidField.scrollIntoView({
                behavior: 'smooth',
                block: 'center'
            });

            setTimeout(() => {
                firstInvalidField.focus();
            }, 400);
        }

        return isValid;
    }

    if (nextBtn) {
        nextBtn.addEventListener('click', function () {
            if (!validateCurrentStep()) {
                return;
            }

            if (currentStep < totalSteps) {
                currentStep += 1;
                showStep(currentStep);
            }
        });
    }

    if (prevBtn) {
        prevBtn.addEventListener('click', function () {
            if (currentStep > 1) {
                currentStep -= 1;
                showStep(currentStep);
            }
        });
    }

    /**
     * اگر بعد از submit خطای سمت سرور وجود داشت،
     * کاربر را به اولین مرحله دارای خطا می‌بریم.
     */
    function goToStepWithServerErrors() {
        const errorLists = document.querySelectorAll('.errorlist');

        if (!errorLists.length) {
            return false;
        }

        const firstError = errorLists[0];
        const errorPanel = firstError.closest('.complete-step-panel');

        if (!errorPanel) {
            return false;
        }

        const step = Number(errorPanel.dataset.step);

        if (!step) {
            return false;
        }

        currentStep = step;
        showStep(currentStep);

        return true;
    }

    const hasServerErrorStep = goToStepWithServerErrors();

    if (!hasServerErrorStep) {
        showStep(currentStep);
    }


(function () {
    const meta = document.getElementById('cargo-meta');
    if (!meta) return;

    const cargoTypeId = meta.dataset.cargoTypeId;
    const subcatUrl   = meta.dataset.subcatUrl;
    const childUrl    = meta.dataset.childUrl;

    const container = document.getElementById('cargo-items-container');
    const addBtn    = document.getElementById('add-cargo-item-btn');

    if (!container || !addBtn) {
        console.error('[CargoItems] عناصر ضروری در صفحه یافت نشد', { container, addBtn });
        return;
    }

    if (!cargoTypeId) {
        console.error('[CargoItems] cargo-type-id خالی است');
    }

    // ── لود زیردسته‌ها برای یک select ──────────────────────────
    function loadSubcategories(selectEl) {
        selectEl.innerHTML = '<option value="">در حال بارگذاری...</option>';
        fetch(`${subcatUrl}?cargo_type=${cargoTypeId}`)
            .then(function(r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            })
            .then(function(data) {
                selectEl.innerHTML = '<option value="">انتخاب کنید...</option>';
                if (!data.length) {
                    selectEl.innerHTML = '<option value="">زیردسته‌ای یافت نشد</option>';
                    return;
                }
                data.forEach(function(s) {
                    const opt = document.createElement('option');
                    opt.value = s.id;
                    opt.textContent = s.name;
                    selectEl.appendChild(opt);
                });
            })
            .catch(function(err) {
                console.error('[CargoItems] خطا در بارگذاری زیردسته‌ها:', err);
                selectEl.innerHTML = '<option value="">خطا در بارگذاری — صفحه را رفرش کنید</option>';
            });
    }

    // ── لود فرزندها بر اساس زیردسته ────────────────────────────
    function loadChildren(subcatId, childSelect, otherWrap) {
        childSelect.disabled = true;
        otherWrap.style.display = 'none';

        if (!subcatId) {
            childSelect.innerHTML = '<option value="">ابتدا زیردسته را انتخاب کنید</option>';
            return;
        }

        childSelect.innerHTML = '<option value="">در حال بارگذاری...</option>';
        fetch(`${childUrl}?subcategory=${subcatId}`)
            .then(function(r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            })
            .then(function(data) {
                childSelect.disabled = false;
                childSelect.innerHTML = '<option value="">انتخاب کنید...</option>';
                data.forEach(function(c) {
                    const opt = document.createElement('option');
                    opt.value = c.id;
                    opt.textContent = c.name;
                    childSelect.appendChild(opt);
                });
            })
            .catch(function(err) {
                console.error('[CargoItems] خطا در بارگذاری نوع کالا:', err);
                childSelect.innerHTML = '<option value="">خطا در بارگذاری</option>';
                childSelect.disabled = false;
            });
    }

    // ── اتصال event ها به یک ردیف ──────────────────────────────
    function bindRow(row) {
        const subSelect   = row.querySelector('.item-subcategory');
        const childSelect = row.querySelector('.item-child');
        const otherWrap   = row.querySelector('.item-other-wrap');
        const deleteBtn   = row.querySelector('.cargo-item-delete-btn');

        if (!subSelect || !childSelect || !otherWrap || !deleteBtn) {
            console.error('[CargoItems] ساختار ردیف کالا ناقص است', row);
            return;
        }

        loadSubcategories(subSelect);

        subSelect.addEventListener('change', function () {
            loadChildren(this.value, childSelect, otherWrap);
        });

        childSelect.addEventListener('change', function () {
            if (this.value === 'other') {
                otherWrap.style.display = '';
            } else {
                otherWrap.style.display = 'none';
                const otherInput = otherWrap.querySelector('.item-other-text');
                if (otherInput) otherInput.value = '';
            }
        });

        deleteBtn.addEventListener('click', function () {
            const rows = container.querySelectorAll('.cargo-item-row');
            if (rows.length > 1) {
                row.remove();
            } else {
                alert('حداقل یک قلم کالا باید وجود داشته باشد.');
            }
        });
    }

    // ── افزودن ردیف جدید ───────────────────────────────────────
    addBtn.addEventListener('click', function () {
        const first = container.querySelector('.cargo-item-row');
        if (!first) return;
        const newRow = first.cloneNode(true);

        newRow.querySelectorAll('select').forEach(function(s) { s.innerHTML = ''; });
        const otherWrap = newRow.querySelector('.item-other-wrap');
        if (otherWrap) {
            otherWrap.style.display = 'none';
            const inp = otherWrap.querySelector('.item-other-text');
            if (inp) inp.value = '';
        }
        const childSel = newRow.querySelector('.item-child');
        if (childSel) {
            childSel.disabled = true;
            childSel.innerHTML = '<option value="">ابتدا زیردسته را انتخاب کنید</option>';
        }

        container.appendChild(newRow);
        bindRow(newRow);
    });

    // ── راه‌اندازی اولیه ردیف اول ──────────────────────────────
    const firstRow = container.querySelector('.cargo-item-row');
    if (firstRow) {
        bindRow(firstRow);
    }
})();

});
