// static/admin_dashboard/js/rate_tier_add.js
// افزودن ردیف جدید به فرم‌ست پلکان‌های نرخ (کلون کردن آخرین ردیف خالی extra=1
// و افزایش TOTAL_FORMS، الگوی استاندارد فرم‌ست‌های داینامیک جنگو).
panelReady(function () {
    var addBtn = document.getElementById('addTierBtn');
    var container = document.getElementById('tiersContainer');
    if (!addBtn || !container) return;

    var totalFormsInput = document.querySelector('input[name$="-TOTAL_FORMS"]');
    if (!totalFormsInput) return;
    var prefix = totalFormsInput.name.replace('-TOTAL_FORMS', '');
    var prefixRe = new RegExp(prefix + '-(\\d+)-');

    addBtn.addEventListener('click', function () {
        var rows = container.querySelectorAll('.tier-row');
        var lastRow = rows[rows.length - 1];
        var newIndex = parseInt(totalFormsInput.value, 10);
        var newRow = lastRow.cloneNode(true);

        newRow.querySelectorAll('input, select').forEach(function (el) {
            ['name', 'id'].forEach(function (attr) {
                if (el.hasAttribute(attr)) {
                    el.setAttribute(attr, el.getAttribute(attr).replace(prefixRe, prefix + '-' + newIndex + '-'));
                }
            });
            if (el.type === 'checkbox') {
                el.checked = false;
            } else if (el.tagName === 'SELECT') {
                el.selectedIndex = 0;
            } else {
                el.value = '';
            }
        });

        container.appendChild(newRow);
        totalFormsInput.value = String(newIndex + 1);
    });
});
