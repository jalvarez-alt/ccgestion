(function () {
    // 1) Mostrar solo las secciones de Persona Natural o Jurídica
    function actualizarTipo() {
        var sel = document.querySelector('input[name="tipo_persona"]:checked');
        var tipo = sel ? sel.value : null;
        document.querySelectorAll('[data-solo]').forEach(function (el) {
            el.classList.toggle('oculto', tipo !== null && el.getAttribute('data-solo') !== tipo);
        });
    }
    document.querySelectorAll('input[name="tipo_persona"]').forEach(function (r) {
        r.addEventListener('change', actualizarTipo);
    });
    actualizarTipo();

    // 2) Patrimonio = activos - pasivos
    function num(s) {
        var d = (s || '').replace(/[^\d-]/g, '');
        return d === '' || d === '-' ? null : parseInt(d, 10);
    }
    [1, 2].forEach(function (n) {
        var a = document.querySelector('[name="fin' + n + '_activos"]');
        var p = document.querySelector('[name="fin' + n + '_pasivos"]');
        var t = document.querySelector('[name="fin' + n + '_patrimonio"]');
        function calc() {
            var x = num(a.value), y = num(p.value);
            t.value = (x !== null && y !== null) ? String(x - y) : '';
        }
        a.addEventListener('input', calc);
        p.addEventListener('input', calc);
    });

    // 3) Firma dibujada
    var canvas = document.getElementById('firma');
    var campo = document.getElementById('firma_img');
    var ctx = canvas.getContext('2d');
    var dibujando = false;

    function fondo() {
        ctx.fillStyle = '#fff';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.strokeStyle = '#111';
        ctx.lineWidth = 2.5;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
    }
    fondo();

    function pos(e) {
        var r = canvas.getBoundingClientRect();
        return {
            x: (e.clientX - r.left) * canvas.width / r.width,
            y: (e.clientY - r.top) * canvas.height / r.height
        };
    }
    canvas.addEventListener('pointerdown', function (e) {
        dibujando = true;
        var p = pos(e);
        ctx.beginPath();
        ctx.moveTo(p.x, p.y);
        canvas.setPointerCapture(e.pointerId);
        e.preventDefault();
    });
    canvas.addEventListener('pointermove', function (e) {
        if (!dibujando) return;
        var p = pos(e);
        ctx.lineTo(p.x, p.y);
        ctx.stroke();
    });
    function terminar() {
        if (!dibujando) return;
        dibujando = false;
        campo.value = canvas.toDataURL('image/png');
    }
    canvas.addEventListener('pointerup', terminar);
    canvas.addEventListener('pointercancel', terminar);

    document.getElementById('limpiar').addEventListener('click', function () {
        fondo();
        campo.value = '';
    });
})();
