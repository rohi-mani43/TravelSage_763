document.addEventListener('DOMContentLoaded', function() {
    // Registration form validation
    const registerForm = document.getElementById('registerForm');
    if (registerForm) {
        registerForm.addEventListener('submit', function(e) {
            const mobile = document.getElementById('mobile').value;
            if (!/^[0-9]{10}$/.test(mobile)) {
                e.preventDefault();
                alert('Please enter a valid 10-digit mobile number');
                return false;
            }
        });
    }

    // Payment form handling
    const paymentForm = document.getElementById('paymentForm');
    if (paymentForm) {
        paymentForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const amount = document.getElementById('amount').value;
            const destinationAddress = document.getElementById('destination_address').value;
            
            if (parseFloat(amount) < 0.0001) {
                alert('Minimum amount is 0.0001 ETH');
                return;
            }
            
            if (!destinationAddress.match(/^0x[a-fA-F0-9]{40}$/)) {
                alert('Please enter a valid Ethereum address');
                return;
            }
            
            try {
                if (typeof window.ethereum === 'undefined') {
                    alert('Please install MetaMask to make cryptocurrency payments');
                    return;
                }
                
                await window.ethereum.request({ method: 'eth_requestAccounts' });
                
                const payButton = document.getElementById('payButton');
                const originalText = payButton.innerHTML;
                payButton.innerHTML = 'Processing...';
                payButton.disabled = true;
                
                this.submit();
                
            } catch (error) {
                alert('Error processing payment: ' + error.message);
                const payButton = document.getElementById('payButton');
                payButton.innerHTML = originalText;
                payButton.disabled = false;
            }
        });
    }
});
