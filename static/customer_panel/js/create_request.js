document.addEventListener('DOMContentLoaded', function() {
    // ── المنت‌های اصلی ──
    const originProvince = document.querySelector('select[name="origin_province"]');
    const originCity     = document.querySelector('select[name="origin_city"]');
    const destCountry    = document.querySelector('select[name="destination_country"]');
    const destCity       = document.querySelector('select[name="destination_city"]');
    const transportMode  = document.querySelector('select[name="transport_mode"]');
    const destPort       = document.querySelector('select[name="destination_port"]');
    const cargoType      = document.querySelector('select[name="cargo_type"]');

    // ── کمکی: پارامترهای مبدا فعلی ──
    function getOriginParams() {
        const cityId     = originCity     ? originCity.value     : '';
        const provinceId = originProvince ? originProvince.value : '';
        let params = '';
        if (cityId)     params += `&origin_city_id=${cityId}`;
        else if (provinceId) params += `&origin_province_id=${provinceId}`;
        return params;
    }

    // ── ریست کمکی ──
    function resetSelect(el, msg) {
        if (!el) return;
        el.innerHTML = `<option value="" disabled selected>${msg}</option>`;
        el.disabled = true;
    }

    function resetDestination() {
        resetSelect(destCountry, 'ابتدا روش حمل را انتخاب کنید');
        resetSelect(destCity,    'ابتدا کشور را انتخاب کنید');
        resetSelect(destPort,    'ابتدا شهر و روش حمل انتخاب شود');
    }

    // ─────────────────────────────────────────────
    // 1. استان مبدا → شهر مبدا (فقط شهرهایی که نرخ فعال دارند)
    // ─────────────────────────────────────────────
    if (originProvince && originCity) {
        if (!originProvince.value) {
            resetSelect(originCity, 'ابتدا استان را انتخاب کنید');
        }

        originProvince.addEventListener('change', function() {
            const provinceId = this.value;
            // وقتی استان عوض شد، شهر و همه مقصدها ریست شوند
            resetSelect(originCity, 'در حال بارگذاری...');
            originCity.disabled = false;
            resetDestination();

            if (!provinceId) {
                resetSelect(originCity, 'ابتدا استان را انتخاب کنید');
                return;
            }

            fetch(`/locations/ajax/cities/?province_id=${provinceId}`)
                .then(r => r.json())
                .then(data => {
                    if (data.length === 0) {
                        resetSelect(originCity, 'شهری با نرخ فعال یافت نشد');
                    } else {
                        originCity.innerHTML = '<option value="">---------</option>';
                        data.forEach(c => {
                            originCity.innerHTML += `<option value="${c.id}">${c.name}</option>`;
                        });
                        originCity.disabled = false;
                    }
                    // بعد از بارگذاری شهرها، کشورها را هم بر اساس استان reload کن
                    loadCountries();
                })
                .catch(err => console.error('خطا در بارگذاری شهرها:', err));
        });
    }

    // ─────────────────────────────────────────────
    // 2. شهر مبدا → کشورهای مقصد را reload کن
    // ─────────────────────────────────────────────
    if (originCity) {
        originCity.addEventListener('change', function() {
            // وقتی شهر مبدا تغییر کرد، مقصد ریست و reload شود
            resetDestination();
            loadCountries();
        });
    }

    // ─────────────────────────────────────────────
    // 3. لود کشورهای مقصد (بر اساس مبدا + روش حمل)
    // ─────────────────────────────────────────────
    const destOriginHint = document.getElementById('dest-origin-hint');

    function isOriginComplete() {
        const mode     = transportMode ? transportMode.value : '';
        const cityId   = originCity    ? originCity.value    : '';
        return !!(mode && cityId);
    }

    function updateDestHint() {
        if (destOriginHint) {
            destOriginHint.style.display = isOriginComplete() ? 'none' : 'inline';
        }
    }

    function loadCountries() {
        if (!destCountry) return;
        const mode   = transportMode ? transportMode.value : '';
        const cityId = originCity    ? originCity.value    : '';

        resetSelect(destCity, 'ابتدا کشور را انتخاب کنید');
        resetSelect(destPort, 'ابتدا شهر و روش حمل انتخاب شود');

        updateDestHint();

        // تا زمانی که مبدا (شهر + روش حمل) کامل نشده، مقصد قفل باشد
        if (!mode || !cityId) {
            resetSelect(destCountry, 'ابتدا اطلاعات مبدا را تکمیل کنید');
            return;
        }

        destCountry.innerHTML = '<option value="">در حال بارگذاری...</option>';
        destCountry.disabled = false;

        const url = `/locations/ajax/countries/?transport_mode=${mode}${getOriginParams()}`;

        fetch(url)
            .then(r => r.json())
            .then(data => {
                if (data.length === 0) {
                    resetSelect(destCountry, 'مقصدی برای این مبدا و روش حمل یافت نشد');
                } else {
                    destCountry.innerHTML = '<option value="">---------</option>';
                    data.forEach(c => {
                        destCountry.innerHTML += `<option value="${c.id}">${c.name}</option>`;
                    });
                    destCountry.disabled = false;
                }
            })
            .catch(err => console.error('خطا در بارگذاری کشورها:', err));
    }

    // ─────────────────────────────────────────────
    // 4. کشور مقصد → شهر مقصد (بر اساس مبدا + روش حمل)
    // ─────────────────────────────────────────────
    if (destCountry && destCity) {
        destCountry.addEventListener('change', function() {
            const countryId = this.value;
            const mode = transportMode ? transportMode.value : '';

            resetSelect(destPort, 'ابتدا شهر و روش حمل انتخاب شود');

            if (!countryId) {
                resetSelect(destCity, 'ابتدا کشور را انتخاب کنید');
                return;
            }

            destCity.innerHTML = '<option value="">در حال بارگذاری...</option>';
            destCity.disabled = false;

            let url = `/locations/ajax/destination-cities/?country_id=${countryId}`;
            if (mode) url += `&transport_mode=${mode}`;
            url += getOriginParams();

            fetch(url)
                .then(r => r.json())
                .then(data => {
                    if (data.length === 0) {
                        resetSelect(destCity, 'شهری با نرخ فعال یافت نشد');
                    } else {
                        destCity.innerHTML = '<option value="">---------</option>';
                        data.forEach(c => {
                            destCity.innerHTML += `<option value="${c.id}">${c.name}</option>`;
                        });
                        destCity.disabled = false;
                    }
                })
                .catch(err => console.error('خطا در بارگذاری شهرهای مقصد:', err));
        });
    }

    // ─────────────────────────────────────────────
    // 5. شهر مقصد → پورت (بر اساس مبدا + روش حمل)
    // ─────────────────────────────────────────────
    function loadPorts() {
        if (!destCity || !destPort || !transportMode) return;

        const cityId = destCity.value;
        const mode   = transportMode.value;
        const prevPort = destPort.value;

        if (!cityId || !mode) {
            resetSelect(destPort, 'ابتدا شهر و روش حمل انتخاب شود');
            return;
        }

        destPort.innerHTML = '<option value="">در حال بارگذاری...</option>';
        destPort.disabled = false;

        const url = `/locations/ajax/ports/?city_id=${cityId}&transport_mode=${mode}${getOriginParams()}`;

        fetch(url)
            .then(r => r.json())
            .then(data => {
                if (data.length === 0) {
                    resetSelect(destPort, 'پورتی با نرخ فعال یافت نشد');
                } else {
                    destPort.innerHTML = '<option value="">---------</option>';
                    data.forEach(p => {
                        const sel = (p.id.toString() === prevPort) ? 'selected' : '';
                        destPort.innerHTML += `<option value="${p.id}" ${sel}>${p.name}</option>`;
                    });
                    if (prevPort) destPort.value = prevPort;
                    destPort.disabled = false;
                }
            })
            .catch(err => console.error('خطا در بارگذاری پورت‌ها:', err));
    }

    // ─────────────────────────────────────────────
    // 6. لود نوع کالا بر اساس روش حمل
    // ─────────────────────────────────────────────
    function loadCargoTypes() {
        if (!transportMode || !cargoType) return;
        const mode = transportMode.value;
        const prevCargo = cargoType.value;

        if (!mode) {
            resetSelect(cargoType, 'ابتدا روش حمل را انتخاب کنید');
            return;
        }

        cargoType.innerHTML = '<option value="">در حال بارگذاری...</option>';
        cargoType.disabled = false;

        fetch(`/orders/ajax/cargo-types/?transport_mode=${mode}`)
            .then(r => r.json())
            .then(data => {
                if (data.length === 0) {
                    resetSelect(cargoType, 'کالایی برای این روش تعریف نشده');
                } else {
                    cargoType.innerHTML = '<option value="">---------</option>';
                    data.forEach(c => {
                        const sel = (c.id.toString() === prevCargo) ? 'selected' : '';
                        cargoType.innerHTML += `<option value="${c.id}" ${sel}>${c.name}</option>`;
                    });
                    if (prevCargo) cargoType.value = prevCargo;
                    cargoType.disabled = false;
                }
            })
            .catch(err => console.error('خطا در بارگذاری نوع کالا:', err));
    }

    // ─────────────────────────────────────────────
    // 7. تغییر روش حمل → همه مقصدها + کالا reload
    // ─────────────────────────────────────────────
    function handleTransportModeChange() {
        if (!transportMode) return;
        const mode = transportMode.value;

        loadCountries();
        loadPorts();
        loadCargoTypes();

        const dimensionsSection = document.getElementById('dimensions-section');
        const containerSection  = document.getElementById('container-section');
        const weightSection     = document.getElementById('weight-section');

        const toggleElements = (section, disable) => {
            if (!section) return;
            section.querySelectorAll('input, select, textarea').forEach(el => {
                if (el.type !== 'hidden' &&
                    !el.name.includes('TOTAL_FORMS') &&
                    !el.name.includes('INITIAL_FORMS')) {
                    el.disabled = disable;
                }
            });
        };

        if (mode === 'sea_fcl' || mode === 'FCL') {
            if (containerSection)  containerSection.style.display  = 'block';
            if (dimensionsSection) dimensionsSection.style.display = 'none';
            if (weightSection)     weightSection.style.display     = 'none';
            toggleElements(dimensionsSection, true);
            toggleElements(weightSection,     true);
            toggleElements(containerSection,  false);
        } else {
            if (containerSection)  containerSection.style.display  = 'none';
            if (dimensionsSection) dimensionsSection.style.display = 'block';
            if (weightSection)     weightSection.style.display     = 'block';
            toggleElements(dimensionsSection, false);
            toggleElements(weightSection,     false);
            toggleElements(containerSection,  true);
        }
    }

    if (destCity)      destCity.addEventListener('change', loadPorts);
    if (transportMode) {
        transportMode.addEventListener('change', handleTransportModeChange);
        handleTransportModeChange(); // اجرای اولیه برای ست کردن وضعیت
    }

    // ─────────────────────────────────────────────
    // 8. Formset داینامیک برای ابعاد
    // ─────────────────────────────────────────────
    const addBtn        = document.getElementById('custom-add-btn');
    const formsContainer = document.getElementById('dimension-forms');
    const totalForms    = document.getElementById('id_dimensions-TOTAL_FORMS');

    function updateFormIndexes() {
        const rows = formsContainer.querySelectorAll('.dimension-form-row');
        if (totalForms) totalForms.value = rows.length;
        rows.forEach((row, index) => {
            row.querySelectorAll('input, select, textarea, label').forEach(el => {
                if (el.id)      el.id      = el.id.replace(/-\d+-/, `-${index}-`);
                if (el.name)    el.name    = el.name.replace(/-\d+-/, `-${index}-`);
                if (el.htmlFor) el.htmlFor = el.htmlFor.replace(/-\d+-/, `-${index}-`);
            });
        });
    }

    if (addBtn && formsContainer && totalForms) {
        addBtn.onclick = function(e) {
            e.preventDefault();
            const rows = formsContainer.querySelectorAll('.dimension-form-row');
            if (rows.length === 0) return;
            const newRow = rows[0].cloneNode(true);
            newRow.querySelectorAll('input, select, textarea').forEach(input => {
                if (input.name.includes('quantity'))    input.value = 1;
                else if (input.type !== 'hidden')       input.value = '';
                else if (input.name.includes('id'))     input.value = '';
            });
            newRow.querySelectorAll('.errorlist').forEach(err => err.remove());
            formsContainer.appendChild(newRow);
            updateFormIndexes();
        };

        formsContainer.onclick = function(e) {
            const deleteBtn = e.target.closest('.delete-row-btn');
            if (deleteBtn) {
                e.preventDefault();
                const rows = formsContainer.querySelectorAll('.dimension-form-row');
                if (rows.length > 1) {
                    deleteBtn.closest('.dimension-form-row').remove();
                    updateFormIndexes();
                } else {
                    alert('حداقل یک ردیف ابعاد باید وجود داشته باشد.');
                }
            }
        };
    }

    // ─────────────────────────────────────────────
    // 9. ارسال AJAX فرم برای محاسبه استعلام
    // ─────────────────────────────────────────────
    const cargoForm      = document.getElementById('cargo-request-form');
    const resultsSection = document.getElementById('results-section');
    const ratesTbody     = document.getElementById('rates-tbody');

    if (cargoForm) {
        cargoForm.addEventListener('submit', function(e) {
            if (document.getElementById('selected_rate_id').value !== '') return;
            e.preventDefault();

            const formData  = new FormData(cargoForm);
            const submitBtn = document.getElementById('calculate-btn');
            submitBtn.disabled  = true;
            submitBtn.innerText = 'در حال محاسبه...';

            fetch('/orders/ajax/calculate-rates/', {
                method:  'POST',
                body:    formData,
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            })
            .then(r => r.json())
            .then(data => {
                submitBtn.disabled  = false;
                submitBtn.innerText = 'محاسبه قیمت (استعلام)';

                if (data.success) {
                    resultsSection.style.display = 'block';
                    document.getElementById('display_actual_weight').innerText =
                        new Intl.NumberFormat('fa-IR').format(data.actual_weight || 0) + ' کیلوگرم';
                    document.getElementById('display_volumetric_weight').innerText =
                        new Intl.NumberFormat('fa-IR').format(data.volumetric_weight || 0) + ' کیلوگرم';
                    document.getElementById('display_chargeable_weight').innerText =
                        new Intl.NumberFormat('fa-IR').format(data.chargeable_weight || 0) + ' کیلوگرم';

                    ratesTbody.innerHTML = '';
                    if (data.rates.length === 0) {
                        ratesTbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">هیچ نرخی یافت نشد.</td></tr>';
                    } else {
                        function renderCharge(type, price) {
                            if (type === 'free')          return '<span class="text-success">رایگان</span>';
                            if (type === 'not_available') return '<span class="text-danger">ارائه نمی‌شود</span>';
                            if (type === 'fixed' || type === 'per_kg')
                                return new Intl.NumberFormat('fa-IR').format(price) + ' ریال';
                            return '-';
                        }
                        data.rates.forEach(rate => {
                            const unitFmt  = new Intl.NumberFormat('fa-IR').format(rate.unit_price)  + ' ریال';
                            const totalFmt = new Intl.NumberFormat('fa-IR').format(rate.total_price) + ' ریال';
                            const vatCell  = rate.add_vat
                                ? new Intl.NumberFormat('fa-IR').format(rate.vat_amount) + ' ریال' : '';
                            const officeCol  = rate.office_packaging_charge_type
                                ? `<td>${renderCharge(rate.office_packaging_charge_type,   rate.office_packaging_price)}</td>`   : '';
                            const onsiteCol  = rate.onsite_packaging_charge_type
                                ? `<td>${renderCharge(rate.onsite_packaging_charge_type,   rate.onsite_packaging_price)}</td>`   : '';
                            const doorstepCol = rate.doorstep_packaging_charge_type
                                ? `<td>${renderCharge(rate.doorstep_packaging_charge_type, rate.doorstep_packaging_price)}</td>` : '';

                            ratesTbody.innerHTML += `
                                <tr>
                                  <td class="forwarder-name">${rate.company_name}</td>
                                  <td class="price-unit">${unitFmt}</td>
                                  ${officeCol}${onsiteCol}${doorstepCol}
                                  <td class="price-vat">${vatCell}</td>
                                  <td class="price-total">${totalFmt}</td>
                                  <td>
                                    <button type="button" class="select-rate-btn"
                                      data-rate-id="${rate.rate_id}"
                                      data-cw="${data.chargeable_weight}"
                                      data-price="${rate.total_price}">
                                      انتخاب و ثبت سفارش
                                    </button>
                                  </td>
                                </tr>`;
                        });
                    }

                    resultsSection.scrollIntoView({ behavior: 'smooth' });

                    const officeHdr   = document.getElementById('office-packaging-header');
                    const onsiteHdr   = document.getElementById('onsite-packaging-header');
                    const doorstepHdr = document.getElementById('doorstep-packaging-header');
                    if (data.rates.length > 0) {
                        if (officeHdr)   officeHdr.style.display   = data.rates[0].office_packaging_charge_type   ? '' : 'none';
                        if (onsiteHdr)   onsiteHdr.style.display   = data.rates[0].onsite_packaging_charge_type   ? '' : 'none';
                        if (doorstepHdr) doorstepHdr.style.display = data.rates[0].doorstep_packaging_charge_type ? '' : 'none';
                    }
                } else {
                    alert('فرم دارای خطا است. لطفاً فیلدهای اجباری را بررسی کنید.');
                    console.log(data.errors);
                }
            })
            .catch(err => {
                submitBtn.disabled  = false;
                submitBtn.innerText = 'محاسبه قیمت (استعلام)';
                console.error('خطا در دریافت نتایج AJAX:', err);
                alert('خطا در برقراری ارتباط با سرور.');
            });
        });

        // 10. کلیک روی "ثبت سفارش"
        ratesTbody.addEventListener('click', function(e) {
            if (e.target.classList.contains('select-rate-btn')) {
                document.getElementById('selected_rate_id').value = e.target.getAttribute('data-rate-id');
                cargoForm.action = '/orders/request/submit/';
                cargoForm.submit();
            }
        });
    }

    // ─────────────────────────────────────────────
    // 11. بسته‌بندی دفتر و محل همزمان انتخاب نشوند
    // ─────────────────────────────────────────────
    const officePackaging = document.querySelector('input[name="needs_office_packaging"]');
    const onsitePackaging = document.querySelector('input[name="needs_onsite_packaging"]');
    if (officePackaging && onsitePackaging) {
        officePackaging.addEventListener('change', function() { if (this.checked) onsitePackaging.checked = false; });
        onsitePackaging.addEventListener('change', function() { if (this.checked) officePackaging.checked = false; });
    }
});
