class CameraController {
    constructor() {
        this.captureBtn = document.getElementById('captureBtn');
        this.previewContainer = document.getElementById('previewContainer');
        this.toast = new bootstrap.Toast(document.getElementById('captureToast'));
        
        this.setupEventListeners();
    }

    setupEventListeners() {
        this.captureBtn.addEventListener('click', () => this.captureImages());
    }

    async captureImages() {
        try {
            this.setLoading(true);
            this.showToast('Capturing images from all cameras...', 'info');

            const response = await fetch('/api/capture', {
                method: 'POST'
            });

            if (!response.ok) throw new Error('Capture failed');

            const data = await response.json();
            this.displayImages(data.images);
            this.showToast('Images captured successfully!', 'success');
        } catch (error) {
            console.error('Capture error:', error);
            this.showToast('Failed to capture images. Please try again.', 'error');
        } finally {
            this.setLoading(false);
        }
    }

    displayImages(images) {
        this.previewContainer.innerHTML = '';
        
        // Sort images by node_id to ensure consistent order
        images.sort((a, b) => a.node_id.localeCompare(b.node_id));
        
        images.forEach(image => {
            const col = document.createElement('div');
            col.className = 'col-md-3 col-sm-6 mb-4';
            
            col.innerHTML = `
                <div class="card h-100">
                    <img src="/received_images/${image.filename}" 
                         class="card-img-top preview-image" 
                         alt="Camera ${image.node_id}"
                         data-bs-toggle="modal"
                         data-bs-target="#imageModal"
                         data-image-src="/received_images/${image.filename}">
                    <div class="card-body">
                        <h5 class="card-title">Camera ${image.node_id}</h5>
                        <p class="card-text text-muted">Click to enlarge</p>
                    </div>
                </div>
            `;
            
            this.previewContainer.appendChild(col);
        });

        // Setup image modal functionality
        this.setupImageModal();
    }

    setupImageModal() {
        const modal = document.getElementById('imageModal');
        if (!modal) return;

        const modalImg = modal.querySelector('.modal-body img');
        document.querySelectorAll('[data-bs-toggle="modal"]').forEach(img => {
            img.addEventListener('click', () => {
                modalImg.src = img.dataset.imageSrc;
            });
        });
    }

    setLoading(isLoading) {
        this.captureBtn.disabled = isLoading;
        this.captureBtn.classList.toggle('loading', isLoading);
        this.captureBtn.innerHTML = isLoading ? 
            '<span class="spinner-border spinner-border-sm me-2"></span>Capturing...' : 
            '<i class="fas fa-camera me-2"></i>Capture Images';
    }

    showToast(message, type = 'info') {
        const toastEl = document.getElementById('captureToast');
        toastEl.querySelector('.toast-body').textContent = message;
        toastEl.className = `toast ${type === 'error' ? 'bg-danger text-white' : 
                                   type === 'success' ? 'bg-success text-white' : ''}`;
        this.toast.show();
    }
}

// Initialize the controller when the page loads
document.addEventListener('DOMContentLoaded', () => {
    new CameraController();
}); 