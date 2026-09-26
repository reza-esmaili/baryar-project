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

    const placeholder = form.querySelector('[data-route-placeholder]');
    if (placeholder) {
      placeholder.hidden = !!scope && (!isIntl || !!direction);
      placeholder.textContent = isIntl ? 'جهت حمل (صادرات یا واردات) را انتخاب کنید.' : 'ابتدا نوع حمل را انتخاب کنید.';
    }

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

  // ─── فرم مرحله‌ای ───────────────────────────────────────────────────────
  const sections = Array.prototype.slice.call(form.querySelectorAll('.step-section'));
  const stepButtons = Array.prototype.slice.call(document.querySelectorAll('.land-step'));
  const lastStep = sections.length;
  let current = 1;
  let furthest = 1;

  function field(name) {
    // تاریخ شمسی مقدار میلادی را در فیلد مخفی نگه می‌دارد
    if (name === 'pickup_date') {
      return document.getElementById('hidden_pickup_date') || document.getElementById('id_pickup_date');
    }
    return form.querySelector('[name="' + name + '"]');
  }

  function value(name) {
    const el = field(name);
    return el && !el.disabled ? String(el.value || '').trim() : '';
  }

  function visibleInput(el) {
    // برای فیلد تاریخ، کادر قابل‌مشاهده علامت می‌خورد نه فیلد مخفی
    if (el && el.id === 'hidden_pickup_date') return document.getElementById('id_pickup_date');
    return el;
  }

  function clearErrors(section) {
    section.querySelectorAll('.is-invalid').forEach(function (el) { el.classList.remove('is-invalid'); });
    section.querySelectorAll('.js-error').forEach(function (el) { el.remove(); });
  }

  function flag(target, message, invalid) {
    if (!target) return;
    target.classList.add('is-invalid');
    const holder = target.closest('.form-group') || target.parentNode;
    if (message && holder && !holder.querySelector('.js-error')) {
      const note = document.createElement('div');
      note.className = 'js-error';
      note.textContent = message;
      holder.appendChild(note);
    }
    invalid.push(target);
  }

  function requireFields(names, invalid) {
    names.forEach(function (name) {
      const el = field(name);
      if (!el || el.disabled) return;
      if (!value(name)) flag(visibleInput(el), 'این فیلد الزامی است.', invalid);
    });
  }

  const validators = {
    1: function (invalid) {
      const scope = checked('scope');
      if (!scope) flag(form.querySelector('[data-required-group="scope"]'), 'نوع حمل را انتخاب کنید.', invalid);
      if (scope === 'international' && !checked('direction')) {
        flag(form.querySelector('[data-required-group="direction"]'), 'جهت حمل را انتخاب کنید.', invalid);
      }
      requireFields(['origin_province', 'origin_city', 'destination_province', 'destination_city', 'foreign_country'], invalid);
      if (scope === 'domestic' && value('origin_city') && value('origin_city') === value('destination_city')) {
        flag(field('destination_city'), 'مبدا و مقصد برون‌شهری باید دو شهر متفاوت باشند.', invalid);
      }
      const foreignCity = field('foreign_city');
      if (foreignCity && !foreignCity.disabled && !value('foreign_city') && !value('foreign_city_name')) {
        flag(foreignCity, 'شهر را انتخاب کنید یا نامش را بنویسید.', invalid);
      }
    },
    2: function (invalid) {
      requireFields(['pickup_address', 'delivery_address', 'pickup_date'], invalid);
    },
    3: function (invalid) {
      requireFields(['cargo_type', 'cargo_description', 'weight_kg', 'vehicle_type'], invalid);
      const weight = parseFloat(value('weight_kg'));
      if (value('weight_kg') && !(weight > 0)) flag(field('weight_kg'), 'وزن باید بیشتر از صفر باشد.', invalid);
    },
    4: function (invalid) {
      requireFields(['sender_name', 'sender_phone', 'receiver_name', 'receiver_phone'], invalid);
    },
    5: function (invalid) {
      requireFields(['proposed_price'], invalid);
      const price = parseInt(value('proposed_price'), 10);
      if (value('proposed_price') && !(price > 0)) flag(field('proposed_price'), 'کرایه باید بیشتر از صفر باشد.', invalid);
    }
  };

  function validateStep(step) {
    const section = sections[step - 1];
    clearErrors(section);
    const invalid = [];
    if (validators[step]) validators[step](invalid);
    return invalid;
  }

  function focusFirst(invalid) {
    const first = invalid[0];
    if (!first) return;
    first.scrollIntoView({ behavior: 'smooth', block: 'center' });
    const focusable = first.matches('input, select, textarea') ? first : first.querySelector('input, select, textarea');
    if (focusable) focusable.focus({ preventScroll: true });
  }

  function showStep(step, options) {
    current = step;
    furthest = Math.max(furthest, step);
    sections.forEach(function (section, index) {
      section.classList.toggle('active', index + 1 === step);
    });
    stepButtons.forEach(function (button, index) {
      const number = index + 1;
      button.classList.toggle('active', number === step);
      button.classList.toggle('is-done', number < step || (number <= furthest && number !== step));
      if (number === step) button.setAttribute('aria-current', 'step');
      else button.removeAttribute('aria-current');
    });
    if (step === lastStep) renderReview();
    if (!options || !options.keepScroll) {
      const nav = document.querySelector('.land-steps');
      if (nav) nav.scrollIntoView({ behavior: 'smooth', block: 'start' });
      const heading = sections[step - 1].querySelector('h2');
      if (heading) heading.focus({ preventScroll: true });
    }
  }

  function goForward() {
    const invalid = validateStep(current);
    if (invalid.length) {
      focusFirst(invalid);
      return false;
    }
    if (current < lastStep) showStep(current + 1);
    return true;
  }

  form.querySelectorAll('[data-next]').forEach(function (button) {
    button.addEventListener('click', goForward);
  });
  form.querySelectorAll('[data-back]').forEach(function (button) {
    button.addEventListener('click', function () { if (current > 1) showStep(current - 1); });
  });
  stepButtons.forEach(function (button) {
    button.addEventListener('click', function () {
      const target = parseInt(button.dataset.goto, 10);
      if (target === current) return;
      // رفتن به عقب آزاد است؛ جلو رفتن فقط تا مرحله‌ای که قبلاً رسیده و با اعتبارسنجی مراحل میانی
      if (target < current) { showStep(target); return; }
      if (target > furthest) return;
      for (let step = current; step < target; step += 1) {
        const invalid = validateStep(step);
        if (invalid.length) { showStep(step); focusFirst(invalid); return; }
      }
      showStep(target);
    });
  });

  // Enter در فیلدهای تک‌خطی به مرحله‌ی بعد می‌رود، نه ارسال زودهنگام فرم
  form.addEventListener('keydown', function (event) {
    const target = event.target;
    if (event.key !== 'Enter' || target.tagName === 'TEXTAREA' || target.type === 'submit') return;
    if (current < lastStep) {
      event.preventDefault();
      goForward();
    }
  });

  form.addEventListener('submit', function (event) {
    if (current < lastStep) {
      event.preventDefault();
      goForward();
      return;
    }
    for (let step = 1; step <= lastStep; step += 1) {
      const invalid = validateStep(step);
      if (invalid.length) {
        event.preventDefault();
        showStep(step);
        focusFirst(invalid);
        return;
      }
    }
    const submit = form.querySelector('button[type="submit"]');
    if (submit) {
      submit.disabled = true;
      submit.innerHTML = '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i> در حال ثبت...';
    }
  });

  form.querySelectorAll('input, select, textarea').forEach(function (input) {
    ['input', 'change'].forEach(function (type) {
      input.addEventListener(type, function () {
        const group = input.closest('[data-required-group]');
        const target = group || (input.id === 'hidden_pickup_date' ? document.getElementById('id_pickup_date') : input);
        if (!target || !target.classList.contains('is-invalid')) return;
        if (group ? input.checked : String(input.value || '').trim()) {
          target.classList.remove('is-invalid');
          const holder = target.closest('.form-group') || target.parentNode;
          const note = holder && holder.querySelector('.js-error');
          if (note) note.remove();
        }
      });
    });
  });

  // ─── خلاصه‌ی بازبینی ────────────────────────────────────────────────────
  function text(name) {
    const el = field(name);
    if (!el || el.disabled) return '';
    if (el.tagName === 'SELECT') {
      const option = el.options[el.selectedIndex];
      return option && option.value ? option.textContent.trim() : '';
    }
    return String(el.value || '').trim();
  }

  function checkedLabel(name) {
    const input = form.querySelector('input[name="' + name + '"]:checked');
    const label = input && input.closest('label');
    const title = label && (label.querySelector('.scope-card__title') || label.querySelector('span'));
    return title ? title.textContent.trim() : '';
  }

  function flags(names) {
    return names
      .filter(function (name) { const el = field(name); return el && !el.disabled && el.checked; })
      .map(function (name) { return field(name).closest('label').textContent.trim(); })
      .join('، ');
  }

  function number(value) {
    const parsed = parseFloat(value);
    return parsed > 0 ? parsed.toLocaleString('fa-IR') : '';
  }

  function routeText() {
    const scope = checked('scope');
    const direction = checked('direction');
    const foreign = [text('foreign_city') || text('foreign_city_name'), text('foreign_country')].filter(Boolean).join('، ');
    if (scope === 'intracity') return [text('origin_city'), ''];
    if (scope === 'international' && direction === 'import') return [foreign, text('destination_city')];
    if (scope === 'international') return [text('origin_city'), foreign];
    return [text('origin_city'), text('destination_city')];
  }

  function renderReview() {
    const box = document.getElementById('land-review');
    if (!box) return;
    const route = routeText();
    const pickupDate = document.getElementById('id_pickup_date');
    const blocks = [
      { step: 1, title: 'نوع حمل و مسیر', rows: [
        ['نوع حمل', [checkedLabel('scope'), checkedLabel('direction')].filter(Boolean).join(' — ')],
        [checked('scope') === 'intracity' ? 'شهر' : 'مبدا', route[0]],
        ['مقصد', route[1]],
        ['مرز ترجیحی', text('border_crossing')],
        ['خدمات گمرکی', flags(['needs_customs_clearance'])]
      ] },
      { step: 2, title: 'آدرس و زمان بارگیری', rows: [
        ['آدرس بارگیری', text('pickup_address')],
        ['آدرس تخلیه', text('delivery_address')],
        ['تاریخ بارگیری', pickupDate ? pickupDate.value : ''],
        ['بازه‌ی زمانی', text('pickup_window')]
      ] },
      { step: 3, title: 'بار و ناوگان', rows: [
        ['کالا', [text('cargo_type'), text('cargo_description')].filter(Boolean).join(' — ')],
        ['وزن', number(value('weight_kg')) ? number(value('weight_kg')) + ' کیلوگرم' : ''],
        ['حجم', number(value('volume_cbm')) ? number(value('volume_cbm')) + ' متر مکعب' : ''],
        ['تعداد بسته', number(value('package_count'))],
        ['بسته‌بندی', text('packaging_type')],
        ['ویژگی‌ها', flags(['is_fragile', 'is_hazardous', 'needs_refrigeration'])],
        ['ناوگان', [text('vehicle_type'), text('loader_type')].filter(Boolean).join(' / ')],
        ['خدمات', flags(['needs_loading_help', 'needs_insurance'])]
      ] },
      { step: 4, title: 'اطلاعات تماس', rows: [
        ['تحویل‌دهنده', [text('sender_name'), text('sender_phone')].filter(Boolean).join(' — ')],
        ['تحویل‌گیرنده', [text('receiver_name'), text('receiver_phone')].filter(Boolean).join(' — ')]
      ] }
    ];

    box.innerHTML = '';
    blocks.forEach(function (block) {
      const card = document.createElement('div');
      card.className = 'review-block';
      const head = document.createElement('div');
      head.className = 'review-block__head';
      const title = document.createElement('h3');
      title.textContent = block.title;
      const edit = document.createElement('button');
      edit.type = 'button';
      edit.className = 'review-edit';
      edit.textContent = 'ویرایش';
      edit.addEventListener('click', function () { showStep(block.step); });
      head.appendChild(title);
      head.appendChild(edit);
      card.appendChild(head);
      block.rows.forEach(function (row) {
        if (!row[1]) return;
        const line = document.createElement('div');
        line.className = 'review-row';
        const label = document.createElement('span');
        label.textContent = row[0];
        const val = document.createElement('b');
        val.textContent = row[1];
        line.appendChild(label);
        line.appendChild(val);
        card.appendChild(line);
      });
      box.appendChild(card);
    });
  }

  // اگر فرم با خطای سرور برگشته، مرحله‌ی اولین خطا باز می‌شود
  const firstServerError = form.querySelector('.field-error');
  if (firstServerError) {
    const section = firstServerError.closest('.step-section');
    const step = section ? parseInt(section.dataset.step, 10) : 1;
    furthest = lastStep;
    showStep(step, { keepScroll: true });
  } else {
    showStep(1, { keepScroll: true });
  }
})();
