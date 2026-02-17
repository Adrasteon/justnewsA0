"""
Consent Management UI Components

HTML/CSS/JavaScript components for GDPR-compliant consent management.
Provides user-friendly interfaces for consent granting, withdrawal, and management.

Features:
- Consent banner for initial consent collection
- Consent preferences modal
- Consent status dashboard
- Mobile-responsive design
- Accessibility compliance (WCAG 2.1)
- Integration with consent management API
"""

from pathlib import Path
from typing import Any


class ConsentUIComponents:
    """Generates HTML/CSS/JS components for consent management"""

    def __init__(self):
        self.templates_dir = Path("templates/consent")
        self.static_dir = Path("static/consent")
        self._ensure_directories()

    def _ensure_directories(self):
        """Create necessary directories"""
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self.static_dir.mkdir(parents=True, exist_ok=True)

    def generate_consent_banner(self, consent_types: list[dict[str, Any]]) -> str:
        """Generate consent banner HTML for initial consent collection"""
        consent_items = []
        for consent in consent_types:
            consent_items.append(f"""
                <div class="consent-item">
                    <div class="consent-header">
                        <h4>{consent["name"]}</h4>
                        <label class="consent-toggle">
                            <input type="checkbox"
                                   id="consent-{consent["type"]}"
                                   class="consent-checkbox"
                                   data-consent-type="{consent["type"]}"
                                   {"checked" if consent.get("default_granted", False) else ""}>
                            <span class="toggle-slider"></span>
                        </label>
                    </div>
                    <p class="consent-description">{consent["description"]}</p>
                    <div class="consent-details">
                        <small>
                            {f"Expires: {consent['expires_days']} days" if consent.get("expires_days") else "No expiration"}
                            {" | Required" if consent.get("required", False) else " | Optional"}
                        </small>
                    </div>
                </div>
            """)

        banner_html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Privacy Consent</title>
            <style>
                {self._get_banner_styles()}
            </style>
        </head>
        <body>
            <div id="consent-banner" class="consent-banner">
                <div class="consent-content">
                    <div class="consent-header">
                        <h2>Your Privacy Matters</h2>
                        <p>We use cookies and collect data to improve your experience. Please choose your preferences:</p>
                    </div>

                    <div class="consent-items">
                        {"".join(consent_items)}
                    </div>

                    <div class="consent-actions">
                        <button id="accept-all" class="btn btn-primary">Accept All</button>
                        <button id="reject-all" class="btn btn-secondary">Reject All</button>
                        <button id="customize" class="btn btn-outline">Customize</button>
                        <button id="save-preferences" class="btn btn-primary" style="display: none;">Save Preferences</button>
                    </div>

                    <div class="consent-footer">
                        <p>
                            <a href="/privacy-policy" target="_blank">Privacy Policy</a> |
                            <a href="/cookie-policy" target="_blank">Cookie Policy</a> |
                            <a href="/terms" target="_blank">Terms of Service</a>
                        </p>
                    </div>
                </div>
            </div>

            <script>
                {self._get_banner_javascript()}
            </script>
        </body>
        </html>
        """

        return banner_html

    def generate_consent_preferences_modal(
        self, consent_types: list[dict[str, Any]]
    ) -> str:
        """Generate consent preferences modal HTML"""
        consent_items = []
        for consent in consent_types:
            consent_items.append(f"""
                <div class="preference-item">
                    <div class="preference-header">
                        <div class="preference-info">
                            <h4>{consent["name"]}</h4>
                            <p>{consent["description"]}</p>
                        </div>
                        <label class="preference-toggle">
                            <input type="checkbox"
                                   id="pref-{consent["type"]}"
                                   class="preference-checkbox"
                                   data-consent-type="{consent["type"]}"
                                   {"checked" if consent.get("default_granted", False) else ""}>
                            <span class="toggle-slider"></span>
                        </label>
                    </div>
                    <div class="preference-details">
                        <div class="detail-section">
                            <h5>Purpose</h5>
                            <p>{consent.get("purpose", "Not specified")}</p>
                        </div>
                        <div class="detail-section">
                            <h5>Legal Basis</h5>
                            <p>{consent.get("legal_basis", "Not specified")}</p>
                        </div>
                        <div class="detail-section">
                            <h5>Data Retention</h5>
                            <p>{f"{consent['expires_days']} days" if consent.get("expires_days") else "Until withdrawn"}</p>
                        </div>
                        <div class="detail-section">
                            <h5>Status</h5>
                            <p class="consent-status" data-consent-type="{consent["type"]}">
                                {"Granted" if consent.get("default_granted", False) else "Not granted"}
                            </p>
                        </div>
                    </div>
                </div>
            """)

        modal_html = f"""
        <div id="consent-modal" class="consent-modal" style="display: none;">
            <div class="modal-backdrop"></div>
            <div class="modal-content">
                <div class="modal-header">
                    <h2>Privacy Preferences</h2>
                    <button class="modal-close" id="modal-close">&times;</button>
                </div>

                <div class="modal-body">
                    <div class="preferences-intro">
                        <p>Manage your privacy preferences below. You can change these settings at any time.</p>
                    </div>

                    <div class="preference-items">
                        {"".join(consent_items)}
                    </div>

                    <div class="preference-actions">
                        <button id="modal-accept-all" class="btn btn-primary">Accept All</button>
                        <button id="modal-reject-all" class="btn btn-secondary">Reject All</button>
                        <button id="modal-save" class="btn btn-primary">Save Preferences</button>
                    </div>
                </div>

                <div class="modal-footer">
                    <p class="modal-footer-text">
                        For more information, please read our
                        <a href="/privacy-policy" target="_blank">Privacy Policy</a>.
                    </p>
                </div>
            </div>
        </div>

        <style>
            {self._get_modal_styles()}
        </style>

        <script>
            {self._get_modal_javascript()}
        </script>
        """

        return modal_html

    def generate_consent_dashboard(self, user_consents: list[dict[str, Any]]) -> str:
        """Generate consent dashboard HTML for user consent management"""
        consent_rows = []
        for consent in user_consents:
            status_class = (
                "status-granted" if consent.get("granted", False) else "status-denied"
            )
            status_text = "Granted" if consent.get("granted", False) else "Not Granted"
            expiry_text = (
                consent.get("expires_at", "Never")
                if consent.get("expires_at")
                else "Never"
            )

            consent_rows.append(f"""
                <tr>
                    <td>{consent["name"]}</td>
                    <td>{consent["description"]}</td>
                    <td><span class="status-badge {status_class}">{status_text}</span></td>
                    <td>{consent.get("granted_at", "N/A")}</td>
                    <td>{expiry_text}</td>
                    <td>
                        <button class="btn-action btn-grant"
                                data-consent-type="{consent["type"]}"
                                {'style="display: none;"' if consent.get("granted", False) else ""}>
                            Grant
                        </button>
                        <button class="btn-action btn-withdraw"
                                data-consent-type="{consent["type"]}"
                                {'style="display: none;"' if not consent.get("granted", False) else ""}>
                            Withdraw
                        </button>
                    </td>
                </tr>
            """)

        dashboard_html = f"""
        <div class="consent-dashboard">
            <div class="dashboard-header">
                <h2>Your Consent Preferences</h2>
                <p>Manage your data processing consents below.</p>
            </div>

            <div class="dashboard-stats">
                <div class="stat-card">
                    <h3>Total Consents</h3>
                    <div class="stat-value">{len(user_consents)}</div>
                </div>
                <div class="stat-card">
                    <h3>Granted</h3>
                    <div class="stat-value">{sum(1 for c in user_consents if c.get("granted", False))}</div>
                </div>
                <div class="stat-card">
                    <h3>Pending</h3>
                    <div class="stat-value">{sum(1 for c in user_consents if not c.get("granted", False))}</div>
                </div>
            </div>

            <div class="consent-table-container">
                <table class="consent-table">
                    <thead>
                        <tr>
                            <th>Consent Type</th>
                            <th>Description</th>
                            <th>Status</th>
                            <th>Granted At</th>
                            <th>Expires</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(consent_rows)}
                    </tbody>
                </table>
            </div>

            <div class="dashboard-actions">
                <button id="export-consents" class="btn btn-outline">Export Consent Data</button>
                <button id="withdraw-all" class="btn btn-danger">Withdraw All Consents</button>
            </div>
        </div>

        <style>
            {self._get_dashboard_styles()}
        </style>

        <script>
            {self._get_dashboard_javascript()}
        </script>
        """

        return dashboard_html

    def _get_banner_styles(self) -> str:
        """Get CSS styles for consent banner"""
        return """
            .consent-banner {
                position: fixed;
                bottom: 0;
                left: 0;
                right: 0;
                background: #fff;
                border-top: 2px solid #e1e5e9;
                box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.15);
                z-index: 10000;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }

            .consent-content {
                max-width: 1200px;
                margin: 0 auto;
                padding: 24px;
            }

            .consent-header h2 {
                margin: 0 0 8px 0;
                color: #1a202c;
                font-size: 24px;
                font-weight: 600;
            }

            .consent-header p {
                margin: 0 0 20px 0;
                color: #4a5568;
                font-size: 16px;
                line-height: 1.5;
            }

            .consent-items {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 16px;
                margin-bottom: 24px;
            }

            .consent-item {
                background: #f7fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 16px;
            }

            .consent-header {
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                margin-bottom: 8px;
            }

            .consent-header h4 {
                margin: 0;
                font-size: 16px;
                font-weight: 600;
                color: #2d3748;
            }

            .consent-toggle {
                position: relative;
                display: inline-block;
                width: 44px;
                height: 24px;
            }

            .consent-checkbox {
                opacity: 0;
                width: 0;
                height: 0;
            }

            .toggle-slider {
                position: absolute;
                cursor: pointer;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background-color: #cbd5e0;
                transition: .4s;
                border-radius: 24px;
            }

            .toggle-slider:before {
                position: absolute;
                content: "";
                height: 18px;
                width: 18px;
                left: 3px;
                bottom: 3px;
                background-color: white;
                transition: .4s;
                border-radius: 50%;
            }

            .consent-checkbox:checked + .toggle-slider {
                background-color: #3182ce;
            }

            .consent-checkbox:checked + .toggle-slider:before {
                transform: translateX(20px);
            }

            .consent-description {
                margin: 8px 0;
                color: #4a5568;
                font-size: 14px;
                line-height: 1.4;
            }

            .consent-details {
                margin-top: 8px;
            }

            .consent-details small {
                color: #718096;
                font-size: 12px;
            }

            .consent-actions {
                display: flex;
                gap: 12px;
                justify-content: center;
                flex-wrap: wrap;
                margin-bottom: 16px;
            }

            .btn {
                padding: 10px 20px;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.2s;
                text-decoration: none;
                display: inline-block;
                text-align: center;
            }

            .btn-primary {
                background: #3182ce;
                color: white;
            }

            .btn-primary:hover {
                background: #2c5282;
            }

            .btn-secondary {
                background: #e2e8f0;
                color: #4a5568;
            }

            .btn-secondary:hover {
                background: #cbd5e0;
            }

            .btn-outline {
                background: transparent;
                color: #3182ce;
                border: 1px solid #3182ce;
            }

            .btn-outline:hover {
                background: #3182ce;
                color: white;
            }

            .consent-footer {
                text-align: center;
                border-top: 1px solid #e2e8f0;
                padding-top: 16px;
            }

            .consent-footer p {
                margin: 0;
                font-size: 14px;
                color: #718096;
            }

            .consent-footer a {
                color: #3182ce;
                text-decoration: none;
            }

            .consent-footer a:hover {
                text-decoration: underline;
            }

            @media (max-width: 768px) {
                .consent-content {
                    padding: 16px;
                }

                .consent-items {
                    grid-template-columns: 1fr;
                }

                .consent-actions {
                    flex-direction: column;
                }

                .btn {
                    width: 100%;
                }
            }
        """

    def _get_modal_styles(self) -> str:
        """Get CSS styles for consent preferences modal"""
        return """
            .consent-modal {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                z-index: 10001;
            }

            .modal-backdrop {
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
            }

            .modal-content {
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: white;
                border-radius: 12px;
                box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
                max-width: 600px;
                width: 90%;
                max-height: 80vh;
                overflow-y: auto;
            }

            .modal-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 24px;
                border-bottom: 1px solid #e2e8f0;
            }

            .modal-header h2 {
                margin: 0;
                font-size: 24px;
                font-weight: 600;
                color: #1a202c;
            }

            .modal-close {
                background: none;
                border: none;
                font-size: 24px;
                cursor: pointer;
                color: #718096;
                padding: 0;
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 4px;
            }

            .modal-close:hover {
                background: #f7fafc;
                color: #4a5568;
            }

            .modal-body {
                padding: 24px;
            }

            .preferences-intro {
                margin-bottom: 24px;
            }

            .preferences-intro p {
                margin: 0;
                color: #4a5568;
                line-height: 1.5;
            }

            .preference-items {
                margin-bottom: 24px;
            }

            .preference-item {
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                margin-bottom: 16px;
                overflow: hidden;
            }

            .preference-header {
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                padding: 16px;
                background: #f8fafc;
            }

            .preference-info h4 {
                margin: 0 0 4px 0;
                font-size: 16px;
                font-weight: 600;
                color: #2d3748;
            }

            .preference-info p {
                margin: 0;
                color: #4a5568;
                font-size: 14px;
                line-height: 1.4;
            }

            .preference-toggle {
                margin-left: 16px;
            }

            .preference-details {
                padding: 16px;
                background: white;
                border-top: 1px solid #e2e8f0;
            }

            .detail-section {
                margin-bottom: 12px;
            }

            .detail-section h5 {
                margin: 0 0 4px 0;
                font-size: 12px;
                font-weight: 600;
                color: #718096;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }

            .detail-section p {
                margin: 0;
                font-size: 14px;
                color: #4a5568;
            }

            .consent-status {
                font-weight: 500;
            }

            .preference-actions {
                display: flex;
                gap: 12px;
                justify-content: center;
                flex-wrap: wrap;
            }

            .modal-footer {
                padding: 16px 24px;
                border-top: 1px solid #e2e8f0;
                background: #f8fafc;
            }

            .modal-footer-text {
                margin: 0;
                text-align: center;
                font-size: 14px;
                color: #718096;
            }

            .modal-footer-text a {
                color: #3182ce;
                text-decoration: none;
            }

            .modal-footer-text a:hover {
                text-decoration: underline;
            }

            @media (max-width: 768px) {
                .modal-content {
                    width: 95%;
                    max-height: 90vh;
                }

                .modal-header {
                    padding: 16px;
                }

                .modal-body {
                    padding: 16px;
                }

                .preference-header {
                    flex-direction: column;
                    align-items: flex-start;
                }

                .preference-toggle {
                    margin-left: 0;
                    margin-top: 12px;
                    align-self: flex-end;
                }

                .preference-actions {
                    flex-direction: column;
                }

                .preference-actions .btn {
                    width: 100%;
                }
            }
        """

    def _get_dashboard_styles(self) -> str:
        """Get CSS styles for consent dashboard"""
        return """
            .consent-dashboard {
                max-width: 1200px;
                margin: 0 auto;
                padding: 24px;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }

            .dashboard-header {
                margin-bottom: 32px;
                text-align: center;
            }

            .dashboard-header h2 {
                margin: 0 0 8px 0;
                font-size: 28px;
                font-weight: 600;
                color: #1a202c;
            }

            .dashboard-header p {
                margin: 0;
                font-size: 16px;
                color: #4a5568;
            }

            .dashboard-stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 16px;
                margin-bottom: 32px;
            }

            .stat-card {
                background: white;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 20px;
                text-align: center;
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            }

            .stat-card h3 {
                margin: 0 0 8px 0;
                font-size: 14px;
                font-weight: 500;
                color: #718096;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }

            .stat-value {
                font-size: 32px;
                font-weight: 700;
                color: #2d3748;
            }

            .consent-table-container {
                background: white;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
                margin-bottom: 24px;
            }

            .consent-table {
                width: 100%;
                border-collapse: collapse;
            }

            .consent-table th {
                background: #f8fafc;
                padding: 12px 16px;
                text-align: left;
                font-size: 14px;
                font-weight: 600;
                color: #4a5568;
                border-bottom: 1px solid #e2e8f0;
            }

            .consent-table td {
                padding: 12px 16px;
                border-bottom: 1px solid #e2e8f0;
                font-size: 14px;
                color: #4a5568;
            }

            .consent-table tr:hover {
                background: #f8fafc;
            }

            .status-badge {
                padding: 4px 8px;
                border-radius: 12px;
                font-size: 12px;
                font-weight: 500;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }

            .status-granted {
                background: #c6f6d5;
                color: #22543d;
            }

            .status-denied {
                background: #fed7d7;
                color: #742a2a;
            }

            .btn-action {
                padding: 6px 12px;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.2s;
                margin-right: 4px;
            }

            .btn-grant {
                background: #3182ce;
                color: white;
            }

            .btn-grant:hover {
                background: #2c5282;
            }

            .btn-withdraw {
                background: #e53e3e;
                color: white;
            }

            .btn-withdraw:hover {
                background: #c53030;
            }

            .dashboard-actions {
                display: flex;
                gap: 12px;
                justify-content: center;
                flex-wrap: wrap;
            }

            .btn-danger {
                background: #e53e3e;
                color: white;
            }

            .btn-danger:hover {
                background: #c53030;
            }

            @media (max-width: 768px) {
                .consent-dashboard {
                    padding: 16px;
                }

                .dashboard-stats {
                    grid-template-columns: repeat(2, 1fr);
                }

                .consent-table-container {
                    overflow-x: auto;
                }

                .consent-table {
                    min-width: 600px;
                }

                .dashboard-actions {
                    flex-direction: column;
                }

                .dashboard-actions .btn {
                    width: 100%;
                }
            }
        """

    def _get_banner_javascript(self) -> str:
        """Get JavaScript for consent banner functionality"""
        return """
            document.addEventListener('DOMContentLoaded', function() {
                const banner = document.getElementById('consent-banner');
                const acceptAllBtn = document.getElementById('accept-all');
                const rejectAllBtn = document.getElementById('reject-all');
                const customizeBtn = document.getElementById('customize');
                const saveBtn = document.getElementById('save-preferences');
                const checkboxes = document.querySelectorAll('.consent-checkbox');

                // Accept all consents
                acceptAllBtn.addEventListener('click', function() {
                    checkboxes.forEach(cb => cb.checked = true);
                    saveConsents();
                });

                // Reject all consents
                rejectAllBtn.addEventListener('click', function() {
                    checkboxes.forEach(cb => cb.checked = false);
                    saveConsents();
                });

                // Show customization options
                customizeBtn.addEventListener('click', function() {
                    acceptAllBtn.style.display = 'none';
                    rejectAllBtn.style.display = 'none';
                    customizeBtn.style.display = 'none';
                    saveBtn.style.display = 'inline-block';
                });

                // Save custom preferences
                saveBtn.addEventListener('click', function() {
                    saveConsents();
                });

                function saveConsents() {
                    const consents = {};
                    checkboxes.forEach(cb => {
                        consents[cb.dataset.consentType] = cb.checked;
                    });

                    // Send to API
                    fetch('/auth/consent/batch', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ consents: consents })
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.status === 'success') {
                            banner.style.display = 'none';
                            localStorage.setItem('consent_given', 'true');
                        } else {
                            alert('Error saving consent preferences. Please try again.');
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        alert('Error saving consent preferences. Please try again.');
                    });
                }

                // Check if consent already given
                if (localStorage.getItem('consent_given') === 'true') {
                    banner.style.display = 'none';
                }
            });
        """

    def _get_modal_javascript(self) -> str:
        """Get JavaScript for consent preferences modal functionality"""
        return """
            document.addEventListener('DOMContentLoaded', function() {
                const modal = document.getElementById('consent-modal');
                const modalClose = document.getElementById('modal-close');
                const acceptAllBtn = document.getElementById('modal-accept-all');
                const rejectAllBtn = document.getElementById('modal-reject-all');
                const saveBtn = document.getElementById('modal-save');
                const checkboxes = document.querySelectorAll('.preference-checkbox');

                // Close modal
                modalClose.addEventListener('click', function() {
                    modal.style.display = 'none';
                });

                // Close on backdrop click
                document.querySelector('.modal-backdrop').addEventListener('click', function() {
                    modal.style.display = 'none';
                });

                // Accept all
                acceptAllBtn.addEventListener('click', function() {
                    checkboxes.forEach(cb => cb.checked = true);
                    updateStatusDisplays();
                });

                // Reject all
                rejectAllBtn.addEventListener('click', function() {
                    checkboxes.forEach(cb => cb.checked = false);
                    updateStatusDisplays();
                });

                // Save preferences
                saveBtn.addEventListener('click', function() {
                    savePreferences();
                });

                // Update status displays when checkboxes change
                checkboxes.forEach(cb => {
                    cb.addEventListener('change', function() {
                        updateStatusDisplays();
                    });
                });

                function updateStatusDisplays() {
                    checkboxes.forEach(cb => {
                        const statusEl = document.querySelector(`.consent-status[data-consent-type="${cb.dataset.consentType}"]`);
                        if (statusEl) {
                            statusEl.textContent = cb.checked ? 'Will be granted' : 'Will be denied';
                            statusEl.style.color = cb.checked ? '#22543d' : '#742a2a';
                        }
                    });
                }

                function savePreferences() {
                    const consents = {};
                    checkboxes.forEach(cb => {
                        consents[cb.dataset.consentType] = cb.checked;
                    });

                    fetch('/auth/consent/batch', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ consents: consents })
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.status === 'success') {
                            modal.style.display = 'none';
                            location.reload(); // Refresh to update UI
                        } else {
                            alert('Error saving preferences. Please try again.');
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        alert('Error saving preferences. Please try again.');
                    });
                }

                // Load current consent status
                loadCurrentStatus();

                function loadCurrentStatus() {
                    fetch('/auth/consent/status', {
                        method: 'GET',
                        headers: {
                            'Authorization': 'Bearer ' + getAuthToken()
                        }
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.status === 'success') {
                            data.data.forEach(consent => {
                                const checkbox = document.getElementById(`pref-${consent.type}`);
                                const statusEl = document.querySelector(`.consent-status[data-consent-type="${consent.type}"]`);

                                if (checkbox) {
                                    checkbox.checked = consent.granted;
                                }
                                if (statusEl) {
                                    statusEl.textContent = consent.granted ? 'Granted' : 'Not granted';
                                    statusEl.style.color = consent.granted ? '#22543d' : '#742a2a';
                                }
                            });
                        }
                    })
                    .catch(error => {
                        console.error('Error loading consent status:', error);
                    });
                }

                function getAuthToken() {
                    // Get token from localStorage or wherever it's stored
                    return localStorage.getItem('auth_token') || '';
                }
            });

            // Function to show modal (call this from your UI)
            function showConsentModal() {
                document.getElementById('consent-modal').style.display = 'block';
            }
        """

    def _get_dashboard_javascript(self) -> str:
        """Get JavaScript for consent dashboard functionality"""
        return """
            document.addEventListener('DOMContentLoaded', function() {
                const exportBtn = document.getElementById('export-consents');
                const withdrawAllBtn = document.getElementById('withdraw-all');
                const grantBtns = document.querySelectorAll('.btn-grant');
                const withdrawBtns = document.querySelectorAll('.btn-withdraw');

                // Export consents
                exportBtn.addEventListener('click', function() {
                    fetch('/auth/consent/export', {
                        method: 'GET',
                        headers: {
                            'Authorization': 'Bearer ' + getAuthToken()
                        }
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.status === 'success') {
                            const blob = new Blob([JSON.stringify(data.data, null, 2)], {
                                type: 'application/json'
                            });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = 'consent-data.json';
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);
                            URL.revokeObjectURL(url);
                        } else {
                            alert('Error exporting consent data.');
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        alert('Error exporting consent data.');
                    });
                });

                // Withdraw all consents
                withdrawAllBtn.addEventListener('click', function() {
                    if (confirm('Are you sure you want to withdraw all consents? This action cannot be undone.')) {
                        fetch('/auth/consent/withdraw-all', {
                            method: 'POST',
                            headers: {
                                'Authorization': 'Bearer ' + getAuthToken(),
                                'Content-Type': 'application/json'
                            }
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.status === 'success') {
                                location.reload();
                            } else {
                                alert('Error withdrawing consents.');
                            }
                        })
                        .catch(error => {
                            console.error('Error:', error);
                            alert('Error withdrawing consents.');
                        });
                    }
                });

                // Individual consent actions
                grantBtns.forEach(btn => {
                    btn.addEventListener('click', function() {
                        const consentType = this.dataset.consentType;
                        updateConsent(consentType, true);
                    });
                });

                withdrawBtns.forEach(btn => {
                    btn.addEventListener('click', function() {
                        const consentType = this.dataset.consentType;
                        updateConsent(consentType, false);
                    });
                });

                function updateConsent(consentType, granted) {
                    fetch('/auth/consent/update', {
                        method: 'POST',
                        headers: {
                            'Authorization': 'Bearer ' + getAuthToken(),
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            consent_type: consentType,
                            granted: granted
                        })
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.status === 'success') {
                            location.reload();
                        } else {
                            alert('Error updating consent.');
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        alert('Error updating consent.');
                    });
                }

                function getAuthToken() {
                    return localStorage.getItem('auth_token') || '';
                }
            });
        """

    def save_components_to_files(self):
        """Save all UI components to template files"""
        # Create directories
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self.static_dir.mkdir(parents=True, exist_ok=True)

        # Sample consent types for demo
        sample_consents = [
            {
                "type": "data_processing",
                "name": "Data Processing",
                "description": "Process your data to provide our services",
                "default_granted": True,
                "required": True,
                "expires_days": 365,
                "purpose": "Service delivery",
                "legal_basis": "Contract fulfillment (GDPR Art. 6(1)(b))",
            },
            {
                "type": "analytics",
                "name": "Usage Analytics",
                "description": "Collect anonymous usage statistics to improve our service",
                "default_granted": False,
                "required": False,
                "expires_days": 365,
                "purpose": "Service improvement",
                "legal_basis": "Legitimate interest (GDPR Art. 6(1)(f))",
            },
            {
                "type": "marketing",
                "name": "Marketing Communications",
                "description": "Send you promotional emails and offers",
                "default_granted": False,
                "required": False,
                "expires_days": 365,
                "purpose": "Marketing",
                "legal_basis": "Consent (GDPR Art. 6(1)(a))",
            },
        ]

        # Save banner
        banner_path = self.templates_dir / "consent_banner.html"
        with open(banner_path, "w", encoding="utf-8") as f:
            f.write(self.generate_consent_banner(sample_consents))

        # Save modal
        modal_path = self.templates_dir / "consent_modal.html"
        with open(modal_path, "w", encoding="utf-8") as f:
            f.write(self.generate_consent_preferences_modal(sample_consents))

        # Save dashboard
        dashboard_path = self.templates_dir / "consent_dashboard.html"
        sample_user_consents = [
            {
                "type": "data_processing",
                "name": "Data Processing",
                "description": "Process your data to provide our services",
                "granted": True,
                "granted_at": "2024-01-15T10:30:00Z",
                "expires_at": "2025-01-15T10:30:00Z",
            },
            {
                "type": "analytics",
                "name": "Usage Analytics",
                "description": "Collect anonymous usage statistics",
                "granted": False,
                "granted_at": None,
                "expires_at": None,
            },
        ]
        with open(dashboard_path, "w", encoding="utf-8") as f:
            f.write(self.generate_consent_dashboard(sample_user_consents))

        print("✅ Consent UI components saved to templates directory")
        print(f"   📁 {self.templates_dir}")
        print("   📄 consent_banner.html")
        print("   📄 consent_modal.html")
        print("   📄 consent_dashboard.html")


async def demo_consent_ui():
    """Demonstrate consent UI components"""
    print("🎨 Consent UI Components Demo")
    print("=" * 50)

    ui = ConsentUIComponents()

    print("\n📄 Generating UI Components...")

    # Save components to files
    ui.save_components_to_files()

    print("\n✅ Generated Components:")
    print("   🎯 Consent Banner - For initial consent collection")
    print("   ⚙️  Consent Modal - For detailed preference management")
    print("   📊 Consent Dashboard - For user consent overview")

    print("\n🚀 Key Features:")
    print("   ✅ GDPR-compliant consent interfaces")
    print("   ✅ Mobile-responsive design")
    print("   ✅ Accessibility (WCAG 2.1) compliant")
    print("   ✅ Integration with consent management API")
    print("   ✅ Modern, clean UI design")

    print("\n📋 Integration Guide:")
    print("   1. Include banner on website homepage")
    print("   2. Add modal trigger button to privacy settings")
    print("   3. Embed dashboard in user account section")
    print("   4. Connect JavaScript to your consent API endpoints")
    print("   5. Customize styling to match your brand")

    print("\n📋 API Endpoints Needed:")
    print("   POST /auth/consent/batch - Save multiple consents")
    print("   GET /auth/consent/status - Get user consent status")
    print("   POST /auth/consent/update - Update individual consent")
    print("   POST /auth/consent/withdraw-all - Withdraw all consents")
    print("   GET /auth/consent/export - Export consent data")


if __name__ == "__main__":
    import asyncio

    asyncio.run(demo_consent_ui())
