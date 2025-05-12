import { showToast } from './toast.js';

// Example usage: show a toast when the page loads
window.addEventListener('DOMContentLoaded', () => {
    // showToast('Toast system is working!', 'info'); // Debug message removed

    // Get admin status from a data attribute or global variable
    let currentUserIsAdmin = false;
    if (window.currentUserIsAdmin !== undefined) {
        currentUserIsAdmin = window.currentUserIsAdmin;
    } else if (document.body.dataset.currentUserIsAdmin !== undefined) {
        currentUserIsAdmin = document.body.dataset.currentUserIsAdmin === 'true';
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

    // Admin content form logic
    const adminContentForm = document.getElementById('contentFormAdmin');
    if (adminContentForm) {
        const submitBtnAdmin = document.getElementById('submitBtnAdmin');
        const buttonTextAdmin = document.getElementById('buttonTextAdmin');
        const loadingSpinnerAdmin = document.getElementById('loadingSpinnerAdmin');
        const urlInputAdmin = document.getElementById('urlAdmin');
        const contextInputAdmin = document.getElementById('contextAdmin');

        adminContentForm.addEventListener('submit', async function(e) {
            e.preventDefault();

            if (submitBtnAdmin.disabled) return;

            submitBtnAdmin.disabled = true;
            submitBtnAdmin.classList.add('opacity-75', 'cursor-not-allowed');
            if(buttonTextAdmin) buttonTextAdmin.textContent = 'Processing...';
            if(loadingSpinnerAdmin) loadingSpinnerAdmin.classList.remove('hidden');

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
                    if(urlInputAdmin) urlInputAdmin.value = '';
                    if(contextInputAdmin) contextInputAdmin.value = '';
                } else {
                    showToast(data.error || 'Submission failed. Please try again.', 'error');
                    resetAdminSubmitButton(submitBtnAdmin, buttonTextAdmin, loadingSpinnerAdmin);
                }
            } catch (error) {
                console.error('Error submitting content:', error);
                showToast('An unexpected error occurred. Please try again.', 'error');
                resetAdminSubmitButton(submitBtnAdmin, buttonTextAdmin, loadingSpinnerAdmin);
            }
        });
    }

    function resetAdminSubmitButton(button, textElement, spinnerElement) {
        if(button) button.disabled = false;
        if(button) button.classList.remove('opacity-75', 'cursor-not-allowed');
        if(textElement) textElement.textContent = 'Add Content';
        if(spinnerElement) spinnerElement.classList.add('hidden');
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
                    showToast('Content processed, refresh page to see updates if not visible.', 'info');
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
            console.error('Error polling task status:', error);
            showToast('Error checking content status. Please refresh manually.', 'error');
            resetAdminSubmitButton(submitBtnAdmin, buttonTextAdmin, loadingSpinnerAdmin);
        }
    }

    function addContentCardToPage(item) {
        const contentGrid = document.querySelector('.grid.grid-cols-1.md\\:grid-cols-2.lg\\:grid-cols-3');
        if (!contentGrid) {
            console.error('Content grid not found to add new card.');
            return;
        }
        showToast('Content added! Reloading page to show updates...', 'success');
        setTimeout(() => {
            window.location.reload();
        }, 1500);
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
                const contentCard = createContentCard(item);
                contentContainer.appendChild(contentCard);
            });
            hasMoreContent = data.has_more;
            if (!hasMoreContent) {
                document.getElementById('loadMoreBtn').style.display = 'none';
            }
        } catch (error) {
            console.error('Error loading more content:', error);
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
        button.addEventListener('click', function() {
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
        button.addEventListener('click', function() {
            const contentId = this.dataset.contentId;
            const title = this.dataset.title;
            const excerpt = this.dataset.excerpt;
            const url = this.dataset.url;
            const imageUrl = this.dataset.imageUrl;
            const context = this.dataset.context;
            showEditModal(contentId, title, excerpt, url, imageUrl, context);
        });
    });

    // Edit modal logic
    const editForm = document.getElementById('editForm');
    if (editForm) {
        editForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            const contentId = document.getElementById('editContentId').value;
            const formData = new FormData(this);
            const data = Object.fromEntries(formData.entries());
            delete data.content_id;
            try {
                const response = await fetch(`/api/content/${contentId}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(data)
                });
                if (!response.ok) {
                    throw new Error('Failed to update content');
                }
                const responseData = await response.json();
                showToast('Content updated successfully!', 'success');
                closeEditModal();
                // Update the content card dynamically
                const contentCard = document.querySelector(`[data-content-id="${contentId}"]`).closest('.bg-white');
                if (contentCard) {
                    const titleElement = contentCard.querySelector('h2');
                    const excerptElement = contentCard.querySelector('p.text-gray-600');
                    const urlElement = contentCard.querySelector('a[target="_blank"]');
                    const imageElement = contentCard.querySelector('img');
                    if (titleElement) titleElement.textContent = data.title;
                    if (excerptElement) excerptElement.textContent = data.excerpt;
                    if (urlElement) urlElement.href = data.url;
                    if (imageElement && data.image_url) imageElement.src = data.image_url;
                    const editButton = contentCard.querySelector('.edit-btn');
                    if (editButton) {
                        editButton.dataset.title = data.title;
                        editButton.dataset.excerpt = data.excerpt;
                        editButton.dataset.url = data.url;
                        editButton.dataset.imageUrl = data.image_url;
                        editButton.dataset.context = data.context || '';
                    }
                }
            } catch (error) {
                console.error('Error updating content:', error);
                showToast('Failed to update content. Please try again.', 'error');
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
                console.error('Error deleting content:', error);
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
                const longFormat = new Intl.DateTimeFormat('en-US', { timeZoneName:'short', timeZone }).format(date);
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
            console.error('Error formatting date:', error, 'Input:', isoDateString);
            const now = new Date();
            const year = now.getFullYear();
            const month = String(now.getMonth() + 1).padStart(2, '0');
            const day = String(now.getDate()).padStart(2, '0');
            return `${year}-${month}-${day} (UTC)`;
        }
    }

    // Modal logic (promote, edit)
    window.showPromoteModal = function(contentType, contentId) {
        currentContentType = contentType;
        currentContentId = contentId;
        document.getElementById('promoteModal').classList.remove('hidden');
        document.getElementById('loadingSpinner').classList.remove('hidden');
        document.getElementById('linkedinPost').classList.add('hidden');
        document.getElementById('errorMessage').classList.add('hidden');
        const linkedinTextarea = document.getElementById('linkedinContentEditable');
        linkedinTextarea.value = '';
        const charCounterElement = document.getElementById('charCounter');
        if(charCounterElement) charCounterElement.innerHTML = '';
        generateSocialPost();
    };

    window.closePromoteModal = function() {
        document.getElementById('promoteModal').classList.add('hidden');
        currentContentType = null;
        currentContentId = null;
    };

    async function generateSocialPost() {
        // Show loading spinner immediately
        document.getElementById('loadingSpinner').classList.remove('hidden');
        document.getElementById('linkedinPost').classList.add('hidden');
        document.getElementById('errorMessage').classList.add('hidden');
        
        try {
            // Step 1: Dispatch the task
            const dispatchResponse = await fetch(`/api/promote/${currentContentId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({}) // Empty body as content_id is in URL
            });

            if (!dispatchResponse.ok) {
                const errorData = await dispatchResponse.json().catch(() => ({})); // Catch if .json() fails
                throw new Error(errorData.error || 'Failed to start social media post generation.');
            }
            
            const dispatchData = await dispatchResponse.json();
            const taskId = dispatchData.task_id;

            if (!taskId) {
                throw new Error('Task ID not received for social media post generation.');
            }

            showToast('Social post generation started...', 'info');

            // Step 2: Poll for task status
            pollPromotionTaskStatus(taskId);

        } catch (error) {
            console.error('Error dispatching or starting social post generation:', error);
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

                if (data.linkedin) {
                    document.getElementById('linkedinPost').classList.remove('hidden');
                    const linkedinTextarea = document.getElementById('linkedinContentEditable');
                    linkedinTextarea.value = data.linkedin;
                    linkedinTextarea.addEventListener('input', updateCharacterCount);
                    updateCharacterCount({ target: linkedinTextarea }); // Initial count
                } else {
                    // Handle case where LinkedIn post might be null even on success (e.g., if generation failed for it specifically)
                    const errorDiv = document.getElementById('errorMessage');
                    errorDiv.textContent = 'LinkedIn post could not be generated.';
                    errorDiv.classList.remove('hidden');
                }

                if (data.warnings && data.warnings.length > 0) {
                    const errorDiv = document.getElementById('errorMessage');
                    // Append warnings or set them, depending on desired behavior
                    let currentErrorText = errorDiv.textContent;
                    if (currentErrorText && !errorDiv.classList.contains('hidden')) {
                        currentErrorText += "\n" + data.warnings.join('\n');
                    } else {
                        currentErrorText = data.warnings.join('\n');
                    }
                    errorDiv.textContent = currentErrorText;
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
            console.error('Error polling promotion task status:', error);
            document.getElementById('loadingSpinner').classList.add('hidden');
            const errorDiv = document.getElementById('errorMessage');
            errorDiv.textContent = 'Error checking promotion status. Please try again.';
            errorDiv.classList.remove('hidden');
            showToast('Error checking promotion status.', 'error');
        }
    }

    function updateCharacterCount(event) {
        const textarea = event.target;
        const currentLength = textarea.value.length;
        const charCounterElement = document.getElementById('charCounter');
        const linkedinLimitForDisplay = CHAR_LIMITS.LINKEDIN;
        const isOverLinkedinLimit = currentLength > linkedinLimitForDisplay;
        let counterHTML = `
            <div class="flex justify-between items-center">
                <span class="text-gray-600">Total Length: ${currentLength}</span>
                <span class="${isOverLinkedinLimit ? 'text-red-500' : 'text-gray-600'}">LinkedIn: ${currentLength} / ${linkedinLimitForDisplay}</span>
            </div>
        `;
        if (charCounterElement) {
            charCounterElement.innerHTML = counterHTML;
        }
    }

    // Edit modal helpers
    window.showEditModal = function(contentId, title, excerpt, url, imageUrl, context) {
        document.getElementById('editContentId').value = contentId;
        document.getElementById('editTitle').value = title;
        document.getElementById('editExcerpt').value = excerpt;
        document.getElementById('editUrl').value = url;
        document.getElementById('editImageUrl').value = imageUrl;
        document.getElementById('editContext').value = context;
        document.getElementById('editModal').classList.remove('hidden');
    };

    window.closeEditModal = function() {
        document.getElementById('editModal').classList.add('hidden');
    };

}); 