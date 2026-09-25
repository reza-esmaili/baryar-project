(function () {
  'use strict';

  const form = document.getElementById('land-request-form');
  if (!form) return;

  const URLS = window.LAND_URLS || {};

  function checked(name) {
    const el = form.querySelector('input[name="' + name + '"]:checked');
    return el ? el.value : '';
  }

  function show(el, visible) {
    if (!el) return;
    el.hidden = !visible;
    // فیلدهای پنهان در ارسال فرم شرکت نکنند تا داده‌ی ناسازگار ثبت نشود
    el.querySelectorAll('input, select, textarea').forEach(function (input) {
      input.disabled = !visible;
    });
  }

  // ─── نمایش بخش‌ها بر اساس نوع حمل و جهت ─────────────────────────────────
  const originBlock = form.querySelector('[data-block="origin"]');
  const destinationBlock = form.querySelector('[data-block="destination"]');
  const foreignBlock = form.querySelector('[data-block="foreign"]');
  const directionRow = form.querySelector('[data-show-scope="international"]');

  function refreshLayout() {
    const scope = checked('scope');
    const direction = checked('direction');
    const isIntl = scope === 'international';

    show(directionRow, isIntl);
    show(originBlock, scope === 'intracity' || scope === 'domestic' || (isIntl && direction === 'export'));
    show(destinationBlock, scope === 'domestic' || (isIntl && direction === 'import'));
    show(foreignBlock, isIntl && !!direction);

    const originTitle = originBlock && originBlock.querySelector('.route-title');
    if (originTitle) {
      originTitle.textContent = scope === 'intracity' ? originTitle.dataset.labelIntracity : originTitle.dataset.labelDefault;
    }
    const foreignTitle = foreignBlock && foreignBlock.querySelector('.route-title');
    if (foreignTitle && direction) {
      foreignTitle.textContent = direction === 'export' ? foreignTitle.dataset.labelExport : foreignTitle.dataset.labelImport;
    }

    form.querySelectorAll('.scope-card').forEach(function (card) {
      const input = card.querySelector('input');
      card.classList.toggle('is-selected', input && input.checked);
    });
    form.querySelectorAll('.direction-option').forEach(function (opt) {
      const input = opt.querySelector('input');
      opt.classList.toggle('is-selected', input && input.checked);
    });
  }

  form.querySelectorAll('input[name="scope"], input[name="direction"]').forEach(function (input) {
    input.addEventListener('change', refreshLayout);
  });

  // ─── فهرست‌های وابسته ───────────────────────────────────────────────────
  function fillSelect(select, items, placeholder) {
    const previous = select.value;
    select.innerHTML = '';
    const empty = document.createElement('option');
    empty.value = '';
    empty.textContent = placeholder;
    select.appendChild(empty);
    items.forEach(function (item) {
      const opt = document.createElement('option');
      opt.value = item.id;
      opt.textContent = item.name;
      if (String(item.id) === previous) opt.selected = true;
      select.appendChild(opt);
    });
  }

  function load(url, param, value, select, placeholder) {
    if (!select) return;
    if (!value) {
      fillSelect(select, [], placeholder);
      return;
    }
    select.disabled = true;
    fetch(url + '?' + param + '=' + encodeURIComponent(value), { credentials: 'same-origin' })
      .then(function (res) { return res.json(); })
      .then(function (items) { fillSelect(select, items, items.length ? placeholder : 'موردی یافت نشد'); })
      .catch(function () { fillSelect(select, [], 'خطا در دریافت اطلاعات'); })
      .finally(function () { select.disabled = select.closest('[hidden]') !== null; });
  }

  form.querySelectorAll('select[data-city-target]').forEach(function (provinceSelect) {
    const citySelect = document.getElementById(provinceSelect.dataset.cityTarget);
    provinceSelect.addEventListener('change', function () {
      load(URLS.cities, 'province_id', provinceSelect.value, citySelect, 'انتخاب شهر');
    });
    // اگر فرم با خطا برگشته و استان انتخاب شده ولی شهری لود نشده
    if (provinceSelect.value && citySelect && citySelect.options.length <= 1) {
      load(URLS.cities, 'province_id', provinceSelect.value, citySelect, 'انتخاب شهر');
    }
  });

  const countrySelect = document.getElementById('id_foreign_country');
  const foreignCitySelect = document.getElementById('id_foreign_city');
  const borderSelect = document.getElementById('id_border_crossing');
  if (countrySelect) {
    countrySelect.addEventListener('change', function () {
      load(URLS.foreignCities, 'country_id', countrySelect.value, foreignCitySelect, 'انتخاب شهر');
      load(URLS.borders, 'country_id', countrySelect.value, borderSelect, 'فرقی نمی‌کند');
    });
  }

  // ─── نمایش کرایه به تومان ───────────────────────────────────────────────
  const priceInput = document.getElementById('id_proposed_price');
  const priceHint = document.getElementById('price-hint');
  function refreshPriceHint() {
    if (!priceInput || !priceHint) return;
    const rial = parseInt(priceInput.value, 10);
    if (!rial || rial <= 0) {
      priceHint.textContent = '';
      return;
    }
    const toman = Math.floor(rial / 10);
    priceHint.textContent = rial.toLocaleString('fa-IR') + ' ریال — معادل ' + toman.toLocaleString('fa-IR') + ' تومان';
  }
  if (priceInput) {
    priceInput.addEventListener('input', refreshPriceHint);
    refreshPriceHint();
  }

  // ─── تقویم شمسی (مقدار میلادی در فیلد مخفی ارسال می‌شود) ──────────────────
  const dateField = document.getElementById('id_pickup_date');
  if (dateField && window.jQuery && jQuery.fn.persianDatepicker) {
    const hidden = document.createElement('input');
    hidden.type = 'hidden';
    hidden.name = dateField.name;
    hidden.id = 'hidden_pickup_date';
    hidden.value = dateField.value;
    dateField.removeAttribute('name');
    dateField.setAttribute('type', 'text');
    dateField.setAttribute('autocomplete', 'off');
    dateField.parentNode.appendChild(hidden);

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    jQuery(dateField).persianDatepicker({
      format: 'YYYY/MM/DD',
      autoClose: true,
      initialValue: !!hidden.value,
      initialValueType: 'gregorian',
      observer: true,
      minDate: today.getTime(),
      altField: '#hidden_pickup_date',
      altFieldFormatter: function (unix) {
        const d = new Date(unix);
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const dd = String(d.getDate()).padStart(2, '0');
        return d.getFullYear() + '-' + mm + '-' + dd;
      }
    });
    if (hidden.value) {
      jQuery(dateField).persianDatepicker('setDate', new Date(hidden.value + 'T00:00:00').getTime());
    }
  }

  refreshLayout();
})();
