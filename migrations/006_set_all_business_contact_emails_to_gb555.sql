-- Migration: 006_set_all_business_contact_emails_to_gb555
-- Normalizes all business contact emails for demo/test notifications.

UPDATE businesses
SET contact_email = 'gb555@cornell.edu'
WHERE contact_email IS DISTINCT FROM 'gb555@cornell.edu';
