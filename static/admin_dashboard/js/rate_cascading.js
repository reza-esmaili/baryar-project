// static/admin_dashboard/js/rate_cascading.js
// دراپ‌داون‌های وابسته‌ی فرم نرخ (استان→شهر مبدا، کشور→شهر مقصد، شهر مقصد +
// روش حمل → پورت). معادل vanilla-JS همان منطقی که در static/admin/js/rate_form.js
// برای پنل ادمین جنگو با jQuery نوشته شده بود.
panelReady(function () {
    var originProvince = document.getElementById('id_origin_province');
    var originCity = document.getElementById('id_origin_city');
    var destCountry = document.getElementById('id_destination_country');
    var destCity = document.getElementById('id_destination_city');
    var destPort = document.getElementById('id_destination_port');
    var transportMode = document.getElementById('id_transport_mode');

    if (!originProvince && !destCountry) return; // این صفحه فرم نرخ نیست

    function fillOptions(select, items) {
        var html = '<option value="">---------</option>';
        items.forEach(function (item) {
            html += '<option value="' + item.id + '">' + item.name + '</option>';
        });
        select.innerHTML = html;
    }

    function fetchJson(url, params) {
        var query = new URLSearchParams(params).toString();
        return fetch(url + '?' + query, { credentials: 'same-origin' }).then(function (r) { return r.json(); });
    }

    if (originProvince && originCity) {
        originProvince.addEventListener('change', function () {
            var provinceId = originProvince.value;
            if (!provinceId) { fillOptions(originCity, []); return; }
            fetchJson('/staff/ajax/cities/', { province_id: provinceId }).then(function (data) {
                fillOptions(originCity, data);
            });
        });
    }

    if (destCountry && destCity && destPort) {
        destCountry.addEventListener('change', function () {
            fillOptions(destCity, []);
            fillOptions(destPort, []);
            var countryId = destCountry.value;
            if (!countryId) return;
            fetchJson('/staff/ajax/destination-cities/', { country_id: countryId }).then(function (data) {
                fillOptions(destCity, data);
            });
        });
    }

    function updatePorts() {
        if (!destCity || !destPort || !transportMode) return;
        var cityId = destCity.value;
        var mode = transportMode.value;
        if (!cityId || !mode) { fillOptions(destPort, []); return; }
        fetchJson('/staff/ajax/destination-ports/', { city_id: cityId, transport_mode: mode }).then(function (data) {
            fillOptions(destPort, data);
        });
    }

    if (destCity) destCity.addEventListener('change', updatePorts);
    if (transportMode) transportMode.addEventListener('change', updatePorts);
});
