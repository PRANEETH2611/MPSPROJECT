"""
Test script to verify SendGrid email alerting
Run this to send a test email to all configured recipients
"""
import sys
sys.path.append('backend')

from dotenv import load_dotenv
load_dotenv()

from email_service import email_service

if __name__ == '__main__':
    print("📧 SendGrid Email Alert Test")
    print("=" * 50)
    print(f"From: {email_service.from_email}")
    print(f"Recipients: {', '.join(email_service.recipient_emails)}")
    print(f"Enabled: {email_service.enabled}")
    print("=" * 50)
    
    if not email_service.enabled:
        print("❌ Email service not enabled. Check .env file for SENDGRID_API_KEY")
        sys.exit(1)
    
    print("\n🚀 Sending test email...")
    success = email_service.send_test_email()
    
    if success:
        print("✅ Test email sent successfully!")
        print(f"Check your inbox: {', '.join(email_service.recipient_emails)}")
    else:
        print("❌ Failed to send test email. Check server logs for details.")
        sys.exit(1)
