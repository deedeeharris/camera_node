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

        // Create a grid container
        const gridContainer = document.createElement('div');
        gridContainer.className = 'row row-cols-1 row-cols-md-2 g-4';
        
        imageSets.forEach(set => {
            // Only create a set if we have exactly 4 images
            if (set.images.length === 4) {
                const setContainer = document.createElement('div');
                setContainer.className = 'col-lg-6 mb-4';

                // Format timestamp for display
                const formattedTimestamp = this.formatTimestamp(set.timestamp);
                
                // Sort images by node_id for consistent display
                const sortedImages = [...set.images].sort((a, b) => 
                    a.node_id.localeCompare(b.node_id)
                );

                setContainer.innerHTML = `
                    <div class="card h-100">
                        <div class="card-header">
                            <h5 class="mb-0">Set from ${formattedTimestamp}</h5>
                        </div>
                        <div class="card-body">
                            <div class="row g-2">
                                ${sortedImages.map((image, index) => `
                                    <div class="col-6">
                                        <div class="position-relative">
                                            <img src="/received_images/${image.filename}" 
                                                class="img-fluid preview-image" 
                                                alt="Camera ${image.node_id}"
                                                data-bs-toggle="modal"
                                                data-bs-target="#imageModal"
                                                data-image-src="/received_images/${image.filename}">
                                            <div class="position-absolute bottom-0 start-0 bg-dark bg-opacity-75 text-white p-1 rounded-end">
                                                Camera ${image.node_id}
                                            </div>
                                        </div>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                        <div class="card-footer">
                            <button class="btn btn-sm btn-outline-primary view-full-set" 
                                    data-timestamp="${set.timestamp}">
                                View Full Size
                            </button>
                        </div>
                    </div>
                `;

                gridContainer.appendChild(setContainer);
            }
        });

        this.galleryContainer.appendChild(gridContainer);

        // Setup image modal functionality
        this.setupImageModal();
        this.setupFullSetView();
    }

    setupImageModal() {
        const modal = document.getElementById('imageModal');
        if (!modal) return;

        const modalImg = modal.querySelector('.modal-body img');
        document.querySelectorAll('[data-bs-toggle="modal"]').forEach(img => {
            img.addEventListener('click', () => {
                modalImg.src = img.dataset.imageSrc;
                // Update modal title with camera info
                const cameraInfo = img.alt;
                modal.querySelector('.modal-title').textContent = cameraInfo;
            });
        });
    }

    setupFullSetView() {
        document.querySelectorAll('.view-full-set').forEach(button => {
            button.addEventListener('click', () => {
                const card = button.closest('.card');
                const images = card.querySelectorAll('.preview-image');
                const fullScreenContainer = document.createElement('div');
                fullScreenContainer.className = 'full-screen-gallery';
                
                fullScreenContainer.innerHTML = `
                    <div class="full-screen-content">
                        <button class="btn btn-light btn-close-fullscreen">×</button>
                        <div class="row">
                            ${Array.from(images).map(img => `
                                <div class="col-md-6 mb-3">
                                    <img src="${img.dataset.imageSrc}" 
                                         class="img-fluid" 
                                         alt="${img.alt}">
                                    <div class="text-center text-white mt-2">
                                        ${img.alt}
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;

                document.body.appendChild(fullScreenContainer);
                document.body.style.overflow = 'hidden';

                fullScreenContainer.querySelector('.btn-close-fullscreen').addEventListener('click', () => {
                    document.body.removeChild(fullScreenContainer);
                    document.body.style.overflow = '';
                });
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

    formatTimestamp(timestamp) {
        // Parse YYYYMMDD_HHMMSS format
        const year = timestamp.substring(0, 4);
        const month = timestamp.substring(4, 6);
        const day = timestamp.substring(6, 8);
        const hour = timestamp.substring(9, 11);
        const minute = timestamp.substring(11, 13);
        const second = timestamp.substring(13, 15);

        const date = new Date(year, month - 1, day, hour, minute, second);
        return date.toLocaleString();
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new GalleryController();
}); 