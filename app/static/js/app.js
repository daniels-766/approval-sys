/* ═══════════════════════════════════════════════════════════════════════════
   APPROVAL SYSTEM — Client-Side Interactions
   ═══════════════════════════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {

    // ── Format nominal input to currency ──────────────────────────────────
    const nominalInput = document.getElementById('nominal');
    if (nominalInput) {
        nominalInput.addEventListener('input', (e) => {
            let val = e.target.value.replace(/[^0-9]/g, '');
            if (val) {
                val = parseInt(val, 10).toLocaleString('en-IN');
            }
            e.target.value = val;
        });
    }

    // ── File upload preview ───────────────────────────────────────────────
    const fileInput = document.getElementById('document');
    const fileNameDisplay = document.getElementById('file-name-display');
    const uploadArea = document.getElementById('upload-area');

    if (fileInput && fileNameDisplay) {
        fileInput.addEventListener('change', () => {
            if (fileInput.files.length > 0) {
                const fileNames = Array.from(fileInput.files).map((file) => {
                    const sizeMB = (file.size / 1024 / 1024).toFixed(2);
                    return `${file.name} (${sizeMB} MB)`;
                });
                fileNameDisplay.textContent = fileNames.join(', ');
                if (uploadArea) uploadArea.classList.add('dragover');
            } else {
                fileNameDisplay.textContent = '';
                if (uploadArea) uploadArea.classList.remove('dragover');
            }
        });
    }

    // ── Drag & drop visual feedback ───────────────────────────────────────
    if (uploadArea) {
        ['dragenter', 'dragover'].forEach(evt => {
            uploadArea.addEventListener(evt, (e) => {
                e.preventDefault();
                uploadArea.classList.add('dragover');
            });
        });
        ['dragleave', 'drop'].forEach(evt => {
            uploadArea.addEventListener(evt, (e) => {
                e.preventDefault();
                uploadArea.classList.remove('dragover');
            });
        });
    }

    // ── Confirm before approve/reject ─────────────────────────────────────
    document.querySelectorAll('[data-confirm]').forEach(el => {
        el.addEventListener('click', (e) => {
            if (!confirm(el.dataset.confirm)) {
                e.preventDefault();
            }
        });
    });

    // ── Modal logic ───────────────────────────────────────────────────────
    document.querySelectorAll('[data-modal]').forEach(trigger => {
        trigger.addEventListener('click', () => {
            const modal = document.getElementById(trigger.dataset.modal);
            if (modal) modal.classList.add('show');
        });
    });

    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) overlay.classList.remove('show');
        });
    });

    document.querySelectorAll('[data-modal-close]').forEach(btn => {
        btn.addEventListener('click', () => {
            btn.closest('.modal-overlay').classList.remove('show');
        });
    });

    // ── Edit category modal population ────────────────────────────────────
    document.querySelectorAll('[data-edit-category]').forEach(btn => {
        btn.addEventListener('click', () => {
            const id = btn.dataset.editCategory;
            const name = btn.dataset.name;
            const description = btn.dataset.description || '';
            const modal = document.getElementById('editCategoryModal');
            if (modal) {
                modal.classList.add('show');
                const form = modal.querySelector('form');
                if (form) form.action = `/admin/categories/${id}/update`;
                const nameInput = modal.querySelector('#edit-name');
                if (nameInput) nameInput.value = name;
                const descInput = modal.querySelector('#edit-description');
                if (descInput) descInput.value = description;
            }
        });
    });

    // ── Auto-dismiss alerts ───────────────────────────────────────────────
    document.querySelectorAll('.alert').forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            alert.style.transform = 'translateY(-10px)';
            setTimeout(() => alert.remove(), 300);
        }, 5000);
    });
});
