// static/admin_dashboard/js/document_rule_dependent_fields.js
// دراپ‌داون‌های وابسته‌ی فرم قانون مدرک (استان→شهر مبدا، کشور→شهر مقصد،
// شهر مقصد→پورت). معادل vanilla-JS همان
// static/admin/documents/documentrule_dependent_fields.js
panelReady(function () {
    var province = document.getElementById('id_origin_province');
    var city = document.getElementById('id_origin_city');
    var country = document.getElementById('id_destination_country');
    var destCity = document.getElementById('id_destination_city');
    var port = document.getElementById('id_destination_port');

    if (!province && !country) return;

    function resetSelect(select) {
        select.innerHTML = '<option value="">---------</option>';
    }

    function fetchJson(url, params) {
        var query = new URLSearchParams(params).toString();
        return fetch(url + '?' + query, { credentials: 'same-origin' }).then(function (r) { return r.json(); });
    }

    function fillOptions(select, items) {
        items.forEach(function (item) {
            var opt = document.createElement('option');
            opt.value = item.id;
            opt.textContent = item.name;
            select.appendChild(opt);
        });
    }

    if (province && city) {
        province.addEventListener('change', function () {
            resetSelect(city);
            var provinceId = province.value;
            if (!provinceId) return;
            fetchJson('/staff/ajax/cities/', { province_id: provinceId }).then(function (data) {
                fillOptions(city, data);
            });
        });
    }

    if (country && destCity && port) {
        country.addEventListener('change', function () {
            resetSelect(destCity);
            resetSelect(port);
            var countryId = country.value;
            if (!countryId) return;
            fetchJson('/staff/ajax/destination-cities/', { country_id: countryId }).then(function (data) {
                fillOptions(destCity, data);
            });
        });

        destCity.addEventListener('change', function () {
            resetSelect(port);
            var cityId = destCity.value;
            if (!cityId) return;
            fetchJson('/staff/ajax/destination-ports/', { city_id: cityId }).then(function (data) {
                fillOptions(port, data);
            });
        });
    }
});
