// static/admin_dashboard/js/jalali_date_input.js
//
// فیلدهای تاریخ (input[type=date]) صفحه را به تقویم شمسی تبدیل می‌کند. کادر قابل‌مشاهده
// تاریخ شمسی نشان می‌دهد و مقدار میلادی (YYYY-MM-DD) در یک فیلد مخفی با همان name
// ارسال می‌شود، پس فرم و اعتبارسنجی سمت سرور تغییری لازم ندارند.
// نیازمند jQuery، persian-date و persian-datepicker که پیش از این فایل بارگذاری می‌شوند.
panelReady(function () {
    if (!window.jQuery || !jQuery.fn.persianDatepicker) return;

    function toIso(unix) {
        var d = new Date(unix);
        return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
    }

    document.querySelectorAll('#panelMainContent input[type="date"][name]').forEach(function (field) {
        var hidden = document.createElement('input');
        hidden.type = 'hidden';
        hidden.name = field.name;
        hidden.id = (field.id || field.name) + '_gregorian';
        hidden.value = field.value;

        field.removeAttribute('name');
        field.removeAttribute('min');
        field.removeAttribute('max');
        field.type = 'text';
        field.autocomplete = 'off';
        field.placeholder = field.placeholder || 'انتخاب تاریخ';
        // متن میلادی نباید به‌عنوان تاریخ شمسی خوانده شود؛ تاریخ ذخیره‌شده پایین‌تر با setDate اعمال می‌شود
        field.value = '';
        field.parentNode.insertBefore(hidden, field.nextSibling);

        // خروجی این تابع شیء خود تقویم است (نه jQuery)؛ setDate فقط روی همین شیء کار می‌کند.
        // فراخوانی دوباره‌ی persianDatepicker('setDate', ...) تقویم را با تنظیمات پیش‌فرض
        // (تاریخ امروز) از نو می‌سازد و تاریخ ذخیره‌شده از دست می‌رود.
        var picker = jQuery(field).persianDatepicker({
            format: 'YYYY/MM/DD',
            autoClose: true,
            initialValue: false,
            observer: true,
            altField: '#' + hidden.id,
            altFieldFormatter: toIso,
            calendar: { persian: { locale: 'fa' } },
            toolbox: { calendarSwitch: { enabled: false } }
        });
        if (hidden.value && picker && typeof picker.setDate === 'function') {
            picker.setDate(new Date(hidden.value + 'T00:00:00').getTime());
        }

        // پاک کردن کادر یعنی بدون تاریخ؛ مقدار میلادی قبلی نباید جا بماند
        field.addEventListener('input', function () {
            if (!field.value.trim()) hidden.value = '';
        });
    });
});
