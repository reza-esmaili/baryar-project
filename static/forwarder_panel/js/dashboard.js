// statics/forwarder_panel/js/dashboard.js

panelReady(function () {
    // تابعی برای تبدیل اعداد بزرگ به فرمت خوانا (میلیون/میلیارد) مشابه تصویر
    function formatLargeNumbers() {
        const amountElements = document.querySelectorAll('.format-large-number');
        
        amountElements.forEach(el => {
            const value = parseInt(el.getAttribute('data-value'));
            if (!isNaN(value)) {
                if (value >= 1000000000) {
                    const formatted = (value / 1000000000).toFixed(1);
                    el.textContent = formatted + ' میلیارد ریال';
                } else if (value >= 1000000) {
                    const formatted = (value / 1000000).toFixed(1);
                    el.textContent = formatted + ' میلیون ریال';
                } else {
                    el.textContent = value.toLocaleString('fa-IR') + ' ریال';
                }
            }
        });
    }

    formatLargeNumbers();
});
