"""
Professional Email Alerting Service using SendGrid
Sends beautiful HTML email alerts for AIOps monitoring
"""
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from datetime import datetime

class EmailAlertService:
    def __init__(self):
        self.api_key = os.getenv('SENDGRID_API_KEY')
        self.from_email = os.getenv('ALERT_FROM_EMAIL', 'amruthchandra1@gmail.com')
        self.recipient_emails = os.getenv('ALERT_RECIPIENTS', '').split(',')
        self.enabled = bool(self.api_key)
        
        if not self.enabled:
            print("⚠️ SendGrid API key not configured. Email alerts disabled.")
    
    def send_alert(self, alert_type, metric_name, current_value, threshold, severity="CRITICAL"):
        """
        Send professional alert email to all recipients
        
        Args:
            alert_type: Type of alert (e.g., "High CPU Usage")
            metric_name: Name of the metric
            current_value: Current metric value
            threshold: Configured threshold
            severity: CRITICAL, WARNING, or INFO
        """
        if not self.enabled:
            print("❌ Email service not enabled")
            return False
        
        try:
            # Create HTML email content
            html_content = self._create_html_email(
                alert_type, metric_name, current_value, threshold, severity
            )
            
            # Create SendGrid message
            message = Mail(
                from_email=Email(self.from_email, 'AIOps Monitor'),
                to_emails=[To(email.strip()) for email in self.recipient_emails if email.strip()],
                subject=f"🚨 AIOps Alert: {alert_type}",
                html_content=Content("text/html", html_content)
            )
            
            # Send email
            sg = SendGridAPIClient(self.api_key)
            response = sg.send(message)
            
            if response.status_code in [200, 202]:
                print(f"✅ Alert email sent successfully to {len(self.recipient_emails)} recipients")
                return True
            else:
                print(f"⚠️ Email send returned status: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Error sending email: {str(e)}")
            return False
    
    def send_test_email(self):
        """Send a test email to verify configuration"""
        return self.send_alert(
            alert_type="Test Alert",
            metric_name="System Test",
            current_value="N/A",
            threshold="N/A",
            severity="INFO"
        )
    
    def _create_html_email(self, alert_type, metric_name, current_value, threshold, severity):
        """Create beautiful HTML email template"""
        
        # Color coding based on severity
        colors = {
            "CRITICAL": {"bg": "#dc2626", "light": "#fee2e2"},
            "WARNING": {"bg": "#f59e0b", "light": "#fef3c7"},
            "INFO": {"bg": "#3b82f6", "light": "#dbeafe"}
        }
        color = colors.get(severity, colors["CRITICAL"])
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: 'Arial', sans-serif; background-color: #f3f4f6;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f3f4f6; padding: 20px;">
                <tr>
                    <td align="center">
                        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                            
                            <!-- Header -->
                            <tr>
                                <td style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center;">
                                    <h1 style="margin: 0; color: #ffffff; font-size: 28px; font-weight: bold;">
                                        ⚡ AIOps Monitor
                                    </h1>
                                    <p style="margin: 10px 0 0 0; color: #e0e7ff; font-size: 14px;">
                                        Real-Time System Monitoring
                                    </p>
                                </td>
                            </tr>
                            
                            <!-- Alert Badge -->
                            <tr>
                                <td style="padding: 30px; text-align: center; background-color: {color['light']};">
                                    <div style="display: inline-block; background-color: {color['bg']}; color: #ffffff; padding: 12px 24px; border-radius: 8px; font-size: 18px; font-weight: bold;">
                                        🚨 {severity} ALERT
                                    </div>
                                </td>
                            </tr>
                            
                            <!-- Alert Content -->
                            <tr>
                                <td style="padding: 30px;">
                                    <h2 style="margin: 0 0 20px 0; color: #1f2937; font-size: 22px;">
                                        {alert_type}
                                    </h2>
                                    
                                    <table width="100%" cellpadding="12" style="border-collapse: collapse;">
                                        <tr style="background-color: #f9fafb;">
                                            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; font-weight: bold; color: #6b7280;">
                                                Metric
                                            </td>
                                            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; color: #1f2937;">
                                                {metric_name}
                                            </td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; font-weight: bold; color: #6b7280;">
                                                Current Value
                                            </td>
                                            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; color: {color['bg']}; font-weight: bold; font-size: 18px;">
                                                {current_value}
                                            </td>
                                        </tr>
                                        <tr style="background-color: #f9fafb;">
                                            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; font-weight: bold; color: #6b7280;">
                                                Threshold
                                            </td>
                                            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; color: #1f2937;">
                                                {threshold}
                                            </td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 12px; font-weight: bold; color: #6b7280;">
                                                Timestamp
                                            </td>
                                            <td style="padding: 12px; color: #1f2937;">
                                                {timestamp}
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>
                            
                            <!-- Recommendations -->
                            <tr>
                                <td style="padding: 20px 30px; background-color: #f9fafb;">
                                    <h3 style="margin: 0 0 10px 0; color: #1f2937; font-size: 16px;">
                                        💡 Recommended Actions
                                    </h3>
                                    <ul style="margin: 0; padding-left: 20px; color: #6b7280; line-height: 1.6;">
                                        <li>Check the dashboard for detailed metrics</li>
                                        <li>Review recent deployments or changes</li>
                                        <li>Consider scaling resources if needed</li>
                                        <li>Investigate potential bottlenecks</li>
                                    </ul>
                                </td>
                            </tr>
                            
                            <!-- CTA Button -->
                            <tr>
                                <td style="padding: 30px; text-align: center;">
                                    <a href="http://localhost:5000/dashboard" 
                                       style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: bold; font-size: 16px;">
                                        📊 View Dashboard
                                    </a>
                                </td>
                            </tr>
                            
                            <!-- Footer -->
                            <tr>
                                <td style="padding: 20px; text-align: center; background-color: #1f2937; color: #9ca3af; font-size: 12px;">
                                    <p style="margin: 0 0 5px 0;">
                                        This is an automated alert from AIOps Monitor
                                    </p>
                                    <p style="margin: 0;">
                                        © 2026 AIOps Monitor. All rights reserved.
                                    </p>
                                </td>
                            </tr>
                            
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        return html

# Singleton instance
email_service = EmailAlertService()
