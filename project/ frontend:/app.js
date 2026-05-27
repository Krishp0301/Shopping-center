function selectMode(mode) {
    document.getElementById('login-form').classList.remove('hidden');
    document.getElementById('mode-title').textContent = 
        mode === 'billing' ? 'Billing Mode Login' : 'Inventory Mode Login';
    document.getElementById('selected-role').value = mode;
}

function handleLogin(e) {
    e.preventDefault();
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    const role = document.getElementById('selected-role').value;
    
    fetch('http://localhost:5000/api/login', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username, password, role})
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            localStorage.setItem('user', JSON.stringify(data.user));
            localStorage.setItem('username', data.user.username);
            localStorage.setItem('role', data.user.role);
            
            if (role === 'billing') {
                window.location.href = 'billing.html';
            } else {
                window.location.href = 'inventory.html';
            }
        } else {
            alert(data.message || 'Login failed');
        }
    })
    .catch(err => {
        alert('Server error. Make sure backend is running at localhost:5000');
    });
}