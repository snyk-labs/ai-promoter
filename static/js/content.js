import { showToast } from './toast.js';

// Example usage: show a toast when the page loads
window.addEventListener('DOMContentLoaded', () => {
    // showToast('Toast system is working!', 'info'); // Debug message removed

    // Get admin status from a data attribute on the body tag
    let currentUserIsAdmin = false;
    if (document.body.dataset.isAdmin !== undefined) {
        currentUserIsAdmin = document.body.dataset.isAdmin === 'true';
    } else if (window.currentUserIsAdmin !== undefined) { // Fallback if needed, though should be removed from HTML
        currentUserIsAdmin = window.currentUserIsAdmin;
    }

    let currentContentId = null;
    let currentContentType = null;
    let currentPage = 1;
    let isLoading = false;
    let hasMoreContent = document.getElementById('loadMoreBtn') !== null;

    // Character limits for platforms
    const CHAR_LIMITS = {
        LINKEDIN: 3000,
        TWITTER: 280,
        BLUESKY: 300,
        URL_APPROX_LENGTH: 30
    };

    // Moved function definition higher
    window.showPromoteModal = function (contentType, contentId) {
        currentContentType = contentType;
        currentContentId = contentId;
        document.getElementById('promoteModal').classList.remove('hidden');
        document.getElementById('loadingSpinner').classList.remove('hidden');
        document.getElementById('linkedinPost').classList.add('hidden');
        document.getElementById('errorMessage').classList.add('hidden');
        const linkedinTextarea = document.getElementById('linkedinContentEditable');
        if (linkedinTextarea) linkedinTextarea.value = '';
        const charCounterElement = document.getElementById('charCounter');
        if (charCounterElement) charCounterElement.innerHTML = '';
        generateSocialPost(); // This function also needs to be defined or moved up if called here
    };

    // Check for promote query parameter and open modal if present
    const urlParams = new URLSearchParams(window.location.search);
    const promoteContentIdFromURL = urlParams.get('promote');
    if (promoteContentIdFromURL) {
        showPromoteModal('content', promoteContentIdFromURL);
    }

    // Admin content form logic
    const adminContentForm = document.getElementById('contentFormAdmin');
    if (adminContentForm) {
        const submitBtnAdmin = document.getElementById('submitBtnAdmin');
        const buttonTextAdmin = document.getElementById('buttonTextAdmin');
        const loadingSpinnerAdmin = document.getElementById('loadingSpinnerAdmin');
        const urlInputAdmin = document.getElementById('urlAdmin');
        const contextInputAdmin = document.getElementById('contextAdmin');
        const copyInputAdmin = document.getElementById('copyAdmin');
        const copyAdminCharCounter = document.getElementById('copyAdminCharCounter');
        const utmCampaignInputAdmin = document.getElementById('utmCampaignAdmin');

        if (copyInputAdmin && copyAdminCharCounter) {
            copyInputAdmin.addEventListener('input', () => updateCharacterCount(copyInputAdmin, copyAdminCharCounter));
            updateCharacterCount(copyInputAdmin, copyAdminCharCounter); // Initial call
        }

        adminContentForm.addEventListener('submit', async function (e) {
            e.preventDefault();

            if (submitBtnAdmin.disabled) return;

            submitBtnAdmin.disabled = true;
            submitBtnAdmin.classList.add('opacity-75', 'cursor-not-allowed');
            if (buttonTextAdmin) buttonTextAdmin.textContent = 'Processing...';
            if (loadingSpinnerAdmin) loadingSpinnerAdmin.classList.remove('hidden');

            const formData = new FormData(adminContentForm);

            try {
                const response = await fetch(adminContentForm.action, {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'Accept': 'application/json'
                    }
                });

                const data = await response.json();

                if (response.ok && data.task_id) {
                    showToast('Content submission received. Processing in background...', 'info');
                    pollTaskStatus(data.task_id, data.content_id);
                    if (urlInputAdmin) urlInputAdmin.value = '';
                    if (contextInputAdmin) contextInputAdmin.value = '';
                    if (copyInputAdmin) copyInputAdmin.value = '';
                    if (utmCampaignInputAdmin) utmCampaignInputAdmin.value = '';
                    if (copyInputAdmin && copyAdminCharCounter) { // Also update counter on clear
                        updateCharacterCount(copyInputAdmin, copyAdminCharCounter);
                    }
                } else {
                    showToast(data.error || 'Submission failed. Please try again.', 'error');
                    resetAdminSubmitButton(submitBtnAdmin, buttonTextAdmin, loadingSpinnerAdmin);
                }
            } catch (error) {
                showToast('An unexpected error occurred. Please try again.', 'error');
                resetAdminSubmitButton(submitBtnAdmin, buttonTextAdmin, loadingSpinnerAdmin);
            }
        });
    }

    function resetAdminSubmitButton(button, textElement, spinnerElement) {
        if (button) button.disabled = false;
        if (button) button.classList.remove('opacity-75', 'cursor-not-allowed');
        if (textElement) textElement.textContent = 'Add Content';
        if (spinnerElement) spinnerElement.classList.add('hidden');
    }

    async function pollTaskStatus(taskId, contentId) {
        const submitBtnAdmin = document.getElementById('submitBtnAdmin');
        const buttonTextAdmin = document.getElementById('buttonTextAdmin');
        const loadingSpinnerAdmin = document.getElementById('loadingSpinnerAdmin');

        try {
            const response = await fetch(`/admin/task_status/${taskId}`);
            const data = await response.json();

            if (data.status === 'SUCCESS') {
                showToast(data.message || 'Content processed successfully!', 'success');
                resetAdminSubmitButton(submitBtnAdmin, buttonTextAdmin, loadingSpinnerAdmin);
                if (data.content) {
                    addContentCardToPage(data.content);
                } else {
                    showToast('Content processed, but could not display automatically. Please refresh.', 'warning');
                }
            } else if (data.status === 'FAILURE') {
                showToast(`Error: ${data.message || 'Content processing failed.'}`, 'error');
                resetAdminSubmitButton(submitBtnAdmin, buttonTextAdmin, loadingSpinnerAdmin);
                const failedCard = document.querySelector(`.card-item[data-card-id='${contentId}']`);
                if (failedCard) {
                    const titleElement = failedCard.querySelector('h2');
                    if (titleElement) titleElement.textContent = 'Processing Failed';
                }
            } else {
                setTimeout(() => pollTaskStatus(taskId, contentId), 3000);
            }
        } catch (error) {
            showToast('Error checking content status. Please refresh manually.', 'error');
            resetAdminSubmitButton(submitBtnAdmin, buttonTextAdmin, loadingSpinnerAdmin);
        }
    }

    function addContentCardToPage(item) {
        const contentGrid = document.querySelector('.grid.grid-cols-1');
        if (!contentGrid) {
            showToast('New content processed. Refreshing page to display.', 'info');
            setTimeout(() => { window.location.reload(); }, 1500);
            return;
        }

        const cardHTML = renderContentCardHTML(item);
        if (cardHTML) {
            contentGrid.insertAdjacentHTML('afterbegin', cardHTML);

            const newCardElement = contentGrid.firstChild;
            if (newCardElement) {
                const promoteBtn = newCardElement.querySelector('.promote-btn');
                if (promoteBtn) {
                    promoteBtn.addEventListener('click', function () {
                        showPromoteModal(this.dataset.contentType, this.dataset.contentId);
                    });
                }

                if (currentUserIsAdmin) {
                    const editBtn = newCardElement.querySelector('.edit-btn');
                    if (editBtn) {
                        editBtn.addEventListener('click', function () {
                            showEditModal(
                                this.dataset.contentId,
                                this.dataset.title,
                                this.dataset.excerpt,
                                this.dataset.url,
                                this.dataset.imageUrl,
                                this.dataset.context,
                                this.dataset.copy,
                                this.dataset.utmCampaign
                            );
                        });
                    }
                    const deleteBtn = newCardElement.querySelector('.delete-content-btn');
                    if (deleteBtn) {
                        deleteBtn.addEventListener('click', handleDeleteContentClick);
                    }
                    const notifyBtn = newCardElement.querySelector('.notify-btn');
                    if (notifyBtn) {
                        notifyBtn.addEventListener('click', function () {
                            const contentId = this.dataset.contentId;
                            const title = this.dataset.title;
                            triggerContentNotification(contentId, title);
                        });
                    }
                }
            }
            showToast('New content added to the page!', 'success');
        } else {
            showToast('Failed to render new content card. Please refresh.', 'warning');
        }
    }

    function renderContentCardHTML(item) {
        if (!item) return '';

        const currentUserIsAdmin = document.body.dataset.isAdmin === 'true'; // Ensure this is correctly scoped

        const imageUrl = item.image_url ? `<img src="${item.image_url}" alt="${item.title || 'Content image'}" class="w-full h-32 object-cover">` : '';
        const title = item.title || 'No Title';
        const submittedBy = item.submitted_by_name ? `<p class="text-sm text-gray-500 mb-2">Submitted by: ${item.submitted_by_name}</p>` : '';

        let submittedDateHTML = '';
        if (item.created_at_iso) {
            const formattedDate = formatDateWithUserTimezone(item.created_at_iso);
            submittedDateHTML = `<p class="text-sm text-gray-500 mb-2 submitted-date-js" data-iso-date="${item.created_at_iso}">Submitted on: ${formattedDate}</p>`;
        }

        let copyPromoUrlHTML = '';
        if (currentUserIsAdmin && item.id) {
            const promoUrl = `${window.location.origin}/?promote=${item.id}`;
            const displayUrl = `/?promote=${item.id}`;
            copyPromoUrlHTML = `
                <p class="text-xs text-gray-400 dark:text-gray-500 mb-2 items-center">
                    Copy Promotion URL: 
                    <span class="font-mono text-gray-500 dark:text-gray-400">${displayUrl}</span>
                    <button class="copy-promo-url-btn ml-1 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200" 
                            data-promo-url="${promoUrl}" 
                            title="Copy promotion URL">
                        <svg class="w-3 h-3 inline-block" fill="currentColor" viewBox="0 0 20 20"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12v-2zM15 5H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h7c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h7v14z"></path></svg>
                    </button>
                </p>
            `;
        }

        const excerpt = (item.excerpt || '').substring(0, 100) + ((item.excerpt || '').length > 100 ? '...' : '');
        const excerptHTML = `<p class="text-gray-600 dark:text-gray-400 mb-4 flex-grow">${excerpt}</p>`;

        let shareSectionHTML = '';
        if (item.share_count > 0) {
            let platformIconsHTML = '';
            if (item.platforms) {
                platformIconsHTML = item.platforms.map(platform => `
                    <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${getPlatformColorJS(platform)}">
                        ${getPlatformIconJS(platform)}
                        ${platform}
                    </span>
                `).join('');
            }
            shareSectionHTML = `
                <div class="mt-2">
                    <p class="text-sm text-gray-500">Shared ${item.share_count} times</p>
                    <div class="flex flex-wrap gap-2 mt-1">
                        ${platformIconsHTML}
                    </div>
                </div>
            `;
        }

        let adminDeleteButtonHTML = '';
        let adminEditButtonHTML = '';
        let adminNotifyButtonHTML = '';

        if (currentUserIsAdmin) {
            adminDeleteButtonHTML = `
                <button 
                    class="delete-content-btn absolute top-2 right-2 text-red-500 hover:text-red-700 font-bold text-2xl z-10"
                    data-content-id="${item.id}"
                    title="Delete Content"
                >
                    &times;
                </button>`;

            adminEditButtonHTML = `
                <button 
                    class="edit-btn px-4 py-2 bg-yellow-500 text-white rounded hover:bg-yellow-600 text-sm"
                    data-content-id="${item.id}"
                    data-title="${item.title || ''}"
                    data-excerpt="${item.excerpt || ''}"
                    data-url="${item.url || ''}"
                    data-image-url="${item.image_url || ''}"
                    data-context="${item.context || ''}" 
                    data-copy="${item.copy || ''}"
                    data-utm-campaign="${item.utm_campaign || ''}"
                >
                    Edit
                </button>`;

            adminNotifyButtonHTML = `
                <button 
                    class="notify-btn absolute top-2 left-2 text-yellow-500 hover:text-yellow-600 z-10"
                    data-content-id="${item.id}"
                    data-title="${item.title || ''}"
                    title="Notify Users"
                >
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"></path>
                    </svg>
                </button>`;
        }

        // Main card structure
        const cardDiv = document.createElement('div');
        cardDiv.className = 'bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden flex flex-col relative card-item max-w-sm';
        cardDiv.dataset.cardId = item.id;

        cardDiv.innerHTML = `
            ${adminDeleteButtonHTML}
            ${adminNotifyButtonHTML}
            ${imageUrl}
            <div class="p-4 flex flex-col flex-grow">
                <h2 class="text-xl font-semibold mb-2 dark:text-gray-100">${title}</h2>
                ${submittedBy}
                ${submittedDateHTML}
                ${copyPromoUrlHTML}
                ${excerptHTML}
                ${shareSectionHTML}
                <div class="flex justify-between items-center space-x-2 mt-auto">
                    <button onclick="window.open('${item.url}', '_blank')" class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm">View</button>
                    ${adminEditButtonHTML}
                    <button 
                        class="promote-btn px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600 text-sm"
                        data-content-type="content" 
                        data-content-id="${item.id}"
                    >
                        Promote
                    </button>
                </div>
            </div>
        `;

        return cardDiv.outerHTML;
    }

    function getPlatformColorJS(platform) {
        if (platform.toLowerCase() === 'linkedin') return 'text-blue-700';
        return 'text-gray-500';
    }

    function getPlatformIconJS(platform) {
        if (platform.toLowerCase() === 'linkedin') return '<path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"/>';
        return '<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"/>';
    }

    // Format dates on initial load
    document.querySelectorAll('.submitted-date-jinja').forEach(el => {
        const isoDate = el.dataset.isoDate;
        if (isoDate) {
            el.textContent = `Submitted on: ${formatDateWithUserTimezone(isoDate)}`;
        }
    });

    // Add event listener for load more button
    const loadMoreBtn = document.getElementById('loadMoreBtn');
    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', loadMoreContent);
    }

    async function loadMoreContent() {
        if (isLoading || !hasMoreContent) return;
        isLoading = true;
        currentPage++;
        try {
            const response = await fetch(`/api/content?page=${currentPage}`);
            if (!response.ok) throw new Error('Failed to load more content');
            const data = await response.json();
            const contentContainer = document.querySelector('.grid');
            data.content.forEach(item => {
                const cardHTML = renderContentCardHTML(item);
                if (cardHTML) {
                    // Insert and get reference to the new card
                    const tempDiv = document.createElement('div');
                    tempDiv.innerHTML = cardHTML;
                    const newCardElement = tempDiv.firstElementChild;
                    contentContainer.appendChild(newCardElement);

                    // Attach event listeners to the new card's buttons
                    const promoteBtn = newCardElement.querySelector('.promote-btn');
                    if (promoteBtn) {
                        promoteBtn.addEventListener('click', function () {
                            showPromoteModal(this.dataset.contentType, this.dataset.contentId);
                        });
                    }
                    if (currentUserIsAdmin) {
                        const editBtn = newCardElement.querySelector('.edit-btn');
                        if (editBtn) {
                            editBtn.addEventListener('click', function () {
                                showEditModal(
                                    this.dataset.contentId,
                                    this.dataset.title,
                                    this.dataset.excerpt,
                                    this.dataset.url,
                                    this.dataset.imageUrl,
                                    this.dataset.context,
                                    this.dataset.copy,
                                    this.dataset.utmCampaign
                                );
                            });
                        }
                        const deleteBtn = newCardElement.querySelector('.delete-content-btn');
                        if (deleteBtn) {
                            deleteBtn.addEventListener('click', handleDeleteContentClick);
                        }
                        const notifyBtn = newCardElement.querySelector('.notify-btn');
                        if (notifyBtn) {
                            notifyBtn.addEventListener('click', function () {
                                const contentId = this.dataset.contentId;
                                const title = this.dataset.title;
                                triggerContentNotification(contentId, title);
                            });
                        }
                    }
                }
            });
            hasMoreContent = data.has_more;
            if (!hasMoreContent) {
                document.getElementById('loadMoreBtn').style.display = 'none';
            }
        } catch (error) {
            // console.error('Error loading more content:', error); // Keep this for now, useful for debugging infinite scroll
        } finally {
            isLoading = false;
        }
    }

    function createContentCard(item) {
        const card = document.createElement('div');
        card.className = 'bg-white rounded-lg shadow-md overflow-hidden hover:shadow-lg transition-shadow duration-300';
        // ... build up card HTML as needed ...
        return card;
    }

    // Add event listeners for promote buttons
    document.querySelectorAll('.promote-btn').forEach(button => {
        button.addEventListener('click', function () {
            currentContentType = this.dataset.contentType;
            currentContentId = this.dataset.contentId;
            showPromoteModal(currentContentType, currentContentId);
        });
    });

    // Add event listeners for delete buttons
    document.querySelectorAll('.delete-content-btn').forEach(button => {
        button.addEventListener('click', handleDeleteContentClick);
    });

    // Add event listeners for edit buttons
    document.querySelectorAll('.edit-btn').forEach(button => {
        button.addEventListener('click', function () {
            const contentId = this.dataset.contentId;
            const title = this.dataset.title;
            const excerpt = this.dataset.excerpt;
            const url = this.dataset.url;
            const imageUrl = this.dataset.imageUrl;
            const context = this.dataset.context;
            const copy = this.dataset.copy;
            const utmCampaign = this.dataset.utmCampaign;
            showEditModal(contentId, title, excerpt, url, imageUrl, context, copy, utmCampaign);
        });
    });

    // Add event listeners for notify buttons
    document.querySelectorAll('.notify-btn').forEach(button => {
        button.addEventListener('click', function () {
            const contentId = this.dataset.contentId;
            const title = this.dataset.title;
            triggerContentNotification(contentId, title);
        });
    });

    // Event delegation for dynamically added copy-promo-url-btn buttons
    const contentGridForPromoCopy = document.querySelector('.grid.grid-cols-1');
    if (contentGridForPromoCopy) {
        contentGridForPromoCopy.addEventListener('click', function (event) {
            const copyButton = event.target.closest('.copy-promo-url-btn');
            if (copyButton) {
                const promoUrl = copyButton.dataset.promoUrl;
                if (promoUrl) {
                    navigator.clipboard.writeText(promoUrl).then(() => {
                        showToast('Promotion URL copied to clipboard!', 'success');
                        // Optional: Provide visual feedback on the button itself
                        const originalIcon = copyButton.innerHTML;
                        copyButton.innerHTML = '<svg class="w-3 h-3 inline-block" fill="currentColor" viewBox="0 0 20 20"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"></path></svg>'; // Checkmark icon
                        setTimeout(() => {
                            copyButton.innerHTML = originalIcon;
                        }, 2000);
                    }).catch(err => {
                        showToast('Failed to copy URL. Please try manually.', 'error');
                    });
                }
            }
        });
    }

    // Edit modal logic
    const editContentForm = document.getElementById('editForm');
    const editModal = document.getElementById('editModal');
    let currentEditContentId = null; // Keep track of the content ID being edited

    // Function to show the edit modal and populate it
    window.showEditModal = function (contentId, title, excerpt, url, imageUrl, context, copy, utmCampaign) {
        currentEditContentId = contentId; // Store the content ID
        document.getElementById('editContentId').value = contentId;
        document.getElementById('editTitle').value = title;
        document.getElementById('editExcerpt').value = excerpt || '';
        document.getElementById('editUrl').value = url;
        document.getElementById('editImageUrl').value = imageUrl || '';
        document.getElementById('editContext').value = context || '';

        const editCopyTextarea = document.getElementById('editCopy');
        const editCopyCharCounter = document.getElementById('editCopyCharCounter');
        editCopyTextarea.value = copy || '';
        updateCharacterCount(editCopyTextarea, editCopyCharCounter);


        document.getElementById('editUtmCampaign').value = utmCampaign || '';
        editModal.classList.remove('hidden');
    };

    // Function to hide the edit modal
    window.hideEditModal = function () {
        editModal.classList.add('hidden');
        currentEditContentId = null; // Clear the content ID when modal is hidden
    };

    if (editContentForm) {
        editContentForm.addEventListener('submit', async function (e) {
            e.preventDefault();

            const contentId = document.getElementById('editContentId').value;

            if (!contentId) {
                showToast('Error: Content ID is missing. Cannot update.', 'error');
                return;
            }

            const formData = new FormData(editContentForm);
            const dataToSend = {};
            formData.forEach((value, key) => {
                const newKey = key.replace(/^edit/, '');
                dataToSend[newKey.charAt(0).toLowerCase() + newKey.slice(1)] = value;
            });

            try {
                const response = await fetch(`/api/content/${contentId}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify(dataToSend)
                });

                const responseText = await response.text(); // Get raw text first for better error diagnosis

                let data;
                try {
                    data = JSON.parse(responseText); // Try to parse
                } catch (parseError) {
                    showToast('Error: Received invalid data from server.', 'error');
                    return;
                }

                if (response.ok && data.content) {
                    showToast('Content updated successfully!', 'success');

                    const card = document.querySelector(`.card-item[data-card-id="${contentId}"]`);
                    if (card) {
                        if (data.content.title) card.querySelector('h2.text-xl').textContent = data.content.title;
                        const excerptEl = card.querySelector('p.text-gray-600');
                        if (excerptEl && data.content.excerpt) {
                            excerptEl.textContent = data.content.excerpt.substring(0, 100) + (data.content.excerpt.length > 100 ? '...' : '');
                        } else if (excerptEl) {
                            excerptEl.textContent = '';
                        }
                        const imgEl = card.querySelector('img');
                        if (imgEl && data.content.image_url) {
                            imgEl.src = data.content.image_url;
                            imgEl.alt = data.content.title || 'Content image';
                        } else if (imgEl) {
                            imgEl.remove();
                        }
                    }

                    const editButton = document.querySelector(`.edit-btn[data-content-id="${contentId}"]`);
                    if (editButton) {
                        editButton.dataset.title = data.content.title || '';
                        editButton.dataset.excerpt = data.content.excerpt || '';
                        editButton.dataset.url = data.content.url || '';
                        editButton.dataset.imageUrl = data.content.image_url || '';
                        editButton.dataset.context = data.content.context || '';
                        editButton.dataset.copy = data.content.copy || '';
                        editButton.dataset.utmCampaign = data.content.utm_campaign || '';
                    }
                    hideEditModal();
                } else {
                    showToast(data.error || 'Update failed. Please try again.', 'error');
                }
            } catch (error) {
                showToast('An unexpected error occurred. Please try again.', 'error');
            }
        });
    }

    async function handleDeleteContentClick(event) {
        const contentId = event.target.dataset.contentId;
        if (!contentId) return;
        if (confirm('Are you sure you want to delete this content item? This action cannot be undone.')) {
            try {
                const response = await fetch(`/api/content/${contentId}`, {
                    method: 'DELETE',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                });
                const result = await response.json();
                if (response.ok) {
                    const cardToRemove = document.querySelector(`.card-item[data-card-id="${contentId}"]`);
                    if (cardToRemove) {
                        cardToRemove.remove();
                    }
                    showToast('Content deleted successfully!', 'success');
                } else {
                    throw new Error(result.error || 'Failed to delete content');
                }
            } catch (error) {
                showToast(error.message || 'An error occurred while deleting the content.', 'error');
            }
        }
    }

    // Helper: format date with user timezone
    function formatDateWithUserTimezone(isoDateString) {
        try {
            const date = new Date(isoDateString);
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
            let timeZoneAbbreviation = '';
            try {
                const longFormat = new Intl.DateTimeFormat('en-US', { timeZoneName: 'short', timeZone }).format(date);
                const match = longFormat.match(/([A-Z]{3,5})$/);
                if (match) {
                    timeZoneAbbreviation = match[1];
                } else {
                    timeZoneAbbreviation = timeZone;
                }
            } catch (e) {
                timeZoneAbbreviation = 'UTC';
            }
            return `${year}-${month}-${day} (${timeZoneAbbreviation})`;
        } catch (error) {
            const now = new Date();
            const year = now.getFullYear();
            const month = String(now.getMonth() + 1).padStart(2, '0');
            const day = String(now.getDate()).padStart(2, '0');
            return `${year}-${month}-${day} (UTC)`; // Fallback, don't log error to console in production
        }
    }

    // Modal logic (promote, edit)
    window.closePromoteModal = function () {
        document.getElementById('promoteModal').classList.add('hidden');
        currentContentType = null;
        currentContentId = null;
    };

    async function triggerContentNotification(contentId, title) {
        if (!contentId || !title) {
            showToast('Cannot notify: Missing content information.', 'error');
            return;
        }

        if (confirm(`Are you sure you want to notify all users about "${title}"? This will send an immediate Slack notification asking them to promote this content.`)) {
            try {
                const response = await fetch(`/api/notify_content/${contentId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    }
                });

                const data = await response.json();

                if (response.ok) {
                    showToast(data.message || 'Notification task triggered successfully!', 'success');
                } else {
                    showToast(data.error || 'Failed to trigger notification task.', 'error');
                }
            } catch (error) {
                showToast('An unexpected error occurred while triggering the notification.', 'error');
                console.error('Error triggering notification:', error);
            }
        }
    }

    async function generateSocialPost() {
        // Show loading spinner immediately
        document.getElementById('loadingSpinner').classList.remove('hidden');
        document.getElementById('linkedinPost').classList.add('hidden');
        document.getElementById('errorMessage').classList.add('hidden');

        let responseText = ''; // To store raw response text
        try {
            // Step 1: Dispatch the task
            const dispatchResponse = await fetch(`/api/promote/${currentContentId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({}) // Empty body as content_id is in URL
            });

            responseText = await dispatchResponse.text(); // Get raw text first

            if (!dispatchResponse.ok) {
                let errorMsg = 'Failed to start social media post generation.';
                try {
                    const errorData = JSON.parse(responseText); // Try to parse the raw text
                    errorMsg = errorData.error || errorMsg;
                } catch (e) {
                    // If parsing fails, use the raw text if it's not too long, or a generic message
                    errorMsg = responseText.substring(0, 200) || errorMsg;
                }
                throw new Error(errorMsg);
            }

            const dispatchData = JSON.parse(responseText); // Parse the logged text for the success case
            const taskId = dispatchData.task_id;

            if (!taskId) {
                throw new Error('Task ID not received for social media post generation.');
            }

            showToast('Social post generation started...', 'info');

            // Step 2: Poll for task status
            pollPromotionTaskStatus(taskId);

        } catch (error) {
            document.getElementById('loadingSpinner').classList.add('hidden');
            const errorDiv = document.getElementById('errorMessage');
            errorDiv.textContent = error.message || 'Failed to start social media post generation. Please try again.';
            errorDiv.classList.remove('hidden');
            showToast(error.message || 'Failed to start post generation.', 'error');
        }
    }

    async function pollPromotionTaskStatus(taskId) {
        try {
            const response = await fetch(`/api/promote_task_status/${taskId}`);
            const data = await response.json();

            if (data.status === 'SUCCESS') {
                document.getElementById('loadingSpinner').classList.add('hidden');
                showToast(data.message || 'Posts generated successfully!', 'success');

                const errorDiv = document.getElementById('errorMessage');
                const linkedinPostDiv = document.getElementById('linkedinPost');
                const postToLinkedInButton = linkedinPostDiv.querySelector('button[onclick="postToLinkedIn()"]');
                const linkedinAuthMessageDiv = document.getElementById('linkedinAuthMessage'); // Assuming this ID will be added to the HTML

                // Reset states
                errorDiv.classList.add('hidden');
                errorDiv.textContent = '';
                linkedinPostDiv.classList.add('hidden');
                if (postToLinkedInButton) postToLinkedInButton.classList.add('hidden');
                if (linkedinAuthMessageDiv) {
                    linkedinAuthMessageDiv.classList.add('hidden');
                    linkedinAuthMessageDiv.innerHTML = ''; // Clear previous message
                }

                let somethingWasDisplayed = false; // To track if any primary content (post or error) is shown

                if (data.linkedin) {
                    linkedinPostDiv.classList.remove('hidden');
                    const linkedinTextarea = document.getElementById('linkedinContentEditable');
                    const charCounterElement = document.getElementById('charCounter'); // Get the specific char counter for promote modal
                    linkedinTextarea.value = data.linkedin;

                    if (linkedinTextarea && charCounterElement) {
                        linkedinTextarea.removeEventListener('input', () => updateCharacterCount(linkedinTextarea, charCounterElement)); // Remove if already exists, ensure correct args
                        linkedinTextarea.addEventListener('input', () => updateCharacterCount(linkedinTextarea, charCounterElement));
                        updateCharacterCount(linkedinTextarea, charCounterElement); // Initial count
                    }
                    somethingWasDisplayed = true;

                    if (data.linkedin_authorized_for_posting) {
                        if (postToLinkedInButton) postToLinkedInButton.classList.remove('hidden');
                    } else {
                        if (postToLinkedInButton) postToLinkedInButton.classList.add('hidden');
                        if (linkedinAuthMessageDiv) {
                            // Construct the profile URL.
                            const profileUrl = '/auth/profile';
                            linkedinAuthMessageDiv.innerHTML = `To enable one-click posting, please <a href="${profileUrl}" class="font-semibold hover:underline">connect your LinkedIn account</a> on your profile page.`;
                            linkedinAuthMessageDiv.classList.remove('hidden');
                        }
                    }
                }

                if (data.warnings && data.warnings.length > 0) {
                    errorDiv.textContent = data.warnings.join('\n');
                    errorDiv.classList.remove('hidden');
                    somethingWasDisplayed = true;
                }

                // If after checking for linkedin post and warnings, nothing is set to be displayed (e.g. post failed to generate and no specific warnings)
                // This case should be less common now that we always try to generate.
                if (!somethingWasDisplayed && !(data.linkedin && data.warnings && data.warnings.length === 0)) {
                    errorDiv.textContent = 'Social media post could not be generated at this time. Please try again later.';
                    errorDiv.classList.remove('hidden');
                }

            } else if (data.status === 'FAILURE') {
                document.getElementById('loadingSpinner').classList.add('hidden');
                const errorDiv = document.getElementById('errorMessage');
                errorDiv.textContent = data.message || 'Social media post generation failed. Please try again.';
                errorDiv.classList.remove('hidden');
                showToast(data.message || 'Post generation failed.', 'error');
            } else { // PENDING or other intermediate states
                // Continue polling
                setTimeout(() => pollPromotionTaskStatus(taskId), 3000);
            }
        } catch (error) {
            document.getElementById('loadingSpinner').classList.add('hidden');
            const errorDiv = document.getElementById('errorMessage');
            errorDiv.textContent = 'Error checking promotion status. Please try again.';
            errorDiv.classList.remove('hidden');
            showToast('Error checking promotion status.', 'error');
        }
    }

    // Generalized function to update character count
    function updateCharacterCount(textareaElement, charCounterElement) {
        if (!textareaElement || !charCounterElement) return;

        const currentLength = textareaElement.value.length;
        const linkedinLimitForDisplay = CHAR_LIMITS.LINKEDIN;
        const isOverLinkedinLimit = currentLength > linkedinLimitForDisplay;

        let counterHTML = `
            <div class="flex justify-between items-center">
                <span class="text-gray-600 dark:text-gray-300">Total Length: ${currentLength}</span>
                <span class="${isOverLinkedinLimit ? 'text-red-500' : 'text-gray-600 dark:text-gray-300'}">LinkedIn: ${currentLength} / ${linkedinLimitForDisplay}</span>
            </div>
        `;
        charCounterElement.innerHTML = counterHTML;
    }

    // Functions for LinkedIn Posting (restored)
    async function postToLinkedIn() {
        const postContent = document.getElementById('linkedinContentEditable').value;
        if (!postContent) {
            showToast('Please enter content to post', 'error');
            return;
        }

        const postButton = document.querySelector('#promoteModal button[onclick="postToLinkedIn()"]'); // More specific selector
        let originalButtonText = '';
        if (postButton) {
            originalButtonText = postButton.textContent;
            postButton.textContent = 'Posting...';
            postButton.disabled = true;
        }

        try {
            const response = await fetch('/auth/linkedin/post', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    post: postContent,
                    content_id: currentContentId // Relies on currentContentId being set when promote modal opens
                })
            });

            const data = await response.json();

            if (!data.success || !data.task_id) { // Check for task_id as well
                throw new Error(data.error || 'Failed to start LinkedIn posting task.');
            }

            showToast('LinkedIn post task started!', 'info');
            pollLinkedInPostStatus(data.task_id);

        } catch (error) {
            showToast(error.message || 'Failed to post to LinkedIn', 'error');
            if (postButton) {
                postButton.textContent = originalButtonText;
                postButton.disabled = false;
            }
        }
    }

    async function pollLinkedInPostStatus(taskId) {
        const postButton = document.querySelector('#promoteModal button[onclick="postToLinkedIn()"]'); // More specific selector
        let originalButtonText = 'Post to LinkedIn'; // Default, might need to get it from button if dynamically set
        if (postButton) originalButtonText = postButton.dataset.originalText || 'Post to LinkedIn'; // Store original text if not already

        try {
            const response = await fetch(`/api/promote_task_status/${taskId}`); // Ensure this endpoint exists and is correct
            const data = await response.json();

            if (data.status === 'SUCCESS') {
                showToast(data.message || 'Posted to LinkedIn successfully!', 'success');
                if (postButton) {
                    postButton.textContent = originalButtonText;
                    postButton.disabled = false;
                }
                // Assuming closePromoteModal is globally available or defined in this scope
                if (typeof closePromoteModal === 'function') {
                    setTimeout(() => {
                        closePromoteModal();
                    }, 2000);
                } else {
                    // console.warn('closePromoteModal function not found after successful LinkedIn post.'); // Keep for dev if needed
                }
            } else if (data.status === 'FAILURE') {
                throw new Error(data.message || 'LinkedIn posting failed');
            } else { // PENDING or other states
                setTimeout(() => pollLinkedInPostStatus(taskId), 3000);
            }
        } catch (error) {
            showToast(error.message || 'Error checking LinkedIn post status', 'error');
            if (postButton) {
                postButton.textContent = originalButtonText;
                postButton.disabled = false;
            }
        }
    }

    // Expose postToLinkedIn globally for inline onclick usage
    window.postToLinkedIn = postToLinkedIn;

}); 