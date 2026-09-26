// static/admin_dashboard/js/document_rule_dynamic.js
// نمایش/پنهان‌سازی فیلدهای شرطی قانون مدرک بر اساس requirement_level.
// معادل vanilla-JS همان static/admin/documents/documentrule_dynamic.js
panelReady(function () {
    var levelField = document.getElementById('id_requirement_level');
    if (!levelField) return;

    var allFields = [
        'shipping_procedure', 'transport_mode',
        'origin_province', 'origin_city',
        'destination_country', 'destination_city', 'destination_port',
        'cargo_type', 'cargo_subcategory'
    ];

    var allowedByLevel = {
        general: [],
        shipping_procedure: ['shipping_procedure'],
        transport_mode: ['transport_mode'],
        origin: ['origin_province', 'origin_city'],
        destination: ['destination_country', 'destination_city', 'destination_port'],
        cargo_type: ['cargo_type'],
        cargo_subcategory: ['cargo_type', 'cargo_subcategory'],
        custom: allFields.slice(),
    };

    function getRow(name) { return document.querySelector('.field-' + name); }
    function getInput(name) { return document.getElementById('id_' + name); }

    function clearField(name) {
        var input = getInput(name);
        if (!input) return;
        if (input.tagName === 'SELECT') {
            input.value = '';
        } else if (input.type === 'checkbox') {
            input.checked = false;
        } else {
            input.value = '';
        }
    }

    function toggleFields() {
        var level = levelField.value;
        var allowed = allowedByLevel[level] || [];
        allFields.forEach(function (name) {
            var row = getRow(name);
            if (allowed.indexOf(name) !== -1) {
                if (row) row.style.display = '';
            } else {
                if (row) row.style.display = 'none';
                clearField(name);
            }
        });
        toggleLandScope();
    }

    // حوزه‌ی حمل زمینی (درون‌شهری/برون‌شهری/بین‌المللی) فقط کنار روش حمل «زمینی» معنا دارد.
    var modeField = getInput('transport_mode');
    function toggleLandScope() {
        var row = getRow('land_scope');
        if (!row) return;
        var modeRow = getRow('transport_mode');
        var visible = modeField && modeField.value === 'land' && (!modeRow || modeRow.style.display !== 'none');
        row.style.display = visible ? '' : 'none';
        if (!visible) clearField('land_scope');
    }

    toggleFields();
    levelField.addEventListener('change', toggleFields);
    if (modeField) modeField.addEventListener('change', toggleLandScope);
});
