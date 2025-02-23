class GalleryController {
    constructor() {
        this.galleryContainer = document.getElementById('galleryContainer');
        this.loadGallery();
    }

    async loadGallery() {
        try {
            const response = await fetch('/api/gallery');
            if (!response.ok) throw new Error('Failed to load gallery');
            
            const imageSets = await response.json();
            this.displayGallery(imageSets);
        } catch (error) {
            console.error('Gallery error:', error);
            this.showError('Failed to load gallery. Please refresh the page.');
        }
    }

    displayGallery(imageSets) {
        this.galleryContainer.innerHTML = '';
        
        if (imageSets.length === 0) {
            this.showMessage('No images captured yet. Go to Capture page to take some photos!');
            return;
        }
        
        imageSets.forEach(set => {
            const setContainer = document.createElement('div');
            setContainer.className = 'image-set';
            
            // Format timestamp for display
            const timestamp = new Date(set.timestamp.replace('_', 'T'));
            
            // Sort images by node_id for consistent display
            const sortedImages = [...set.images].sort((a, b) => 
                a.node_id.localeCompare(b.node_id)
            );
            
            setContainer.innerHTML = `
                <h3 class="mb-3">Set from ${timestamp.toLocaleString()}</h3>
                <div class="row">
                    ${sortedImages.map(image => `
                        <div class="col-md-3 col-sm-6 mb-4">
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
                        </div>
                    `).join('')}
                </div>
            `;
            
            this.galleryContainer.appendChild(setContainer);
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

    showError(message) {
        const alert = document.createElement('div');
        alert.className = 'alert alert-danger';
        alert.textContent = message;
        this.galleryContainer.appendChild(alert);
    }

    showMessage(message) {
        const alert = document.createElement('div');
        alert.className = 'alert alert-info';
        alert.textContent = message;
        this.galleryContainer.appendChild(alert);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new GalleryController();
}); 