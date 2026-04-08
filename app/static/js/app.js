/**
 * 衡策投资系统 - 前端 JS
 */

// 确认操作
function confirmAction(message) {
    return confirm(message || '确定执行此操作吗？');
}

// 表单中的金额自动计算
document.addEventListener('DOMContentLoaded', function() {
    const quantityInput = document.getElementById('quantity');
    const priceInput = document.getElementById('price');
    const amountInput = document.getElementById('amount');

    if (quantityInput && priceInput && amountInput) {
        function calcAmount() {
            const qty = parseFloat(quantityInput.value) || 0;
            const price = parseFloat(priceInput.value) || 0;
            if (qty > 0 && price > 0) {
                amountInput.value = (qty * price).toFixed(2);
            }
        }
        quantityInput.addEventListener('input', calcAmount);
        priceInput.addEventListener('input', calcAmount);
    }
});
