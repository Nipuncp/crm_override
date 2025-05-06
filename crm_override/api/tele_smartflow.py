# Copyright (c) 2023, Sanskartechnolab and contributors
# For license information, please see license.txt

import frappe
import json
import requests


@frappe.whitelist()
def connect_to_call1(agent_number, destination_number):
    # Fetch settings from the single doctype 'Tata Smartflow Settings'
    settings = frappe.get_single("Tata Smartflow Settings")

    if settings.enable_click_to_call:
        auth_token = settings.authentication_token.strip()
        api_url = settings.click_to_call_api_url.strip()
        payload = {
            "agent_number": agent_number,
            "destination_number": destination_number,
        }
        headers = {
            "accept": "application/json",
            "Authorization": auth_token,
            "content-type": "application/json",
        }
        response = requests.post(api_url, json=payload, headers=headers)
        parsed_response = json.dumps(response.json())
        return parsed_response
    else:
        return {
            "success": "false",
            "message": "Please enable the click-to-call from APIs Settings.",
        }


@frappe.whitelist()
def tata_smartflow_webhook():
    """Webhook API that fetches a notification by ID."""
    try:
        user = frappe.session.user

        # Check if user has the required role
        if not has_required_role(user, "tata-smartflow"):
            frappe.local.response.http_status_code = 403
            frappe.response["message"] = "Access Denied: Missing required role"
            frappe.response["success"] = False
            return

        # Parse incoming request data
        data = frappe.request.get_json()
        if not data:
            frappe.local.response.http_status_code = 400
            frappe.response["message"] = "Invalid JSON payload"
            frappe.response["success"] = False
            return

        # Extract fields
        notification_type = "Task"
        mobile_no = data.get("caller_id_number")
        incomming_call_time = data.get("start_stamp")
        # One-line preview message
        preview_text = f"📞 Incoming call from {mobile_no}"
        # Full notification message
        notification_content = (
            f"📞 Incoming Call Alert!\nCaller: {mobile_no}\nTime: {incomming_call_time}"
        )

        # Check if lead exists with this phone number
        lead = frappe.get_all(
            "CRM Lead", filters={"mobile_no": mobile_no}, fields=["name"]
        )
        reference_doctype = "CRM Lead"
        if lead:
            lead_name = lead[0]["name"]
        else:
            # Create a new lead if not found
            new_lead = frappe.get_doc(
                {
                    "doctype": "CRM Lead",
                    "first_name": f"Unknown {mobile_no}",
                    "mobile_no": str(mobile_no),
                    "status": "New",
                    "source": "Call",
                }
            )
            new_lead.ignore_mandatory = True
            new_lead.insert(ignore_permissions=True)
            lead_name = new_lead.name

        # Fetch all active users
        system_users = frappe.get_all("User", filters={"enabled": 1}, pluck="name")

        # Create notifications for all users
        for system_user in system_users:
            notification = frappe.get_doc(
                {
                    "doctype": "CRM Notification",
                    "from_user": user,
                    "to_user": system_user,
                    "type": notification_type,
                    "message": notification_content,
                    "notification_text": preview_text,
                    "reference_doctype": reference_doctype,
                    "reference_name": lead_name,
                    "read": 0,  # Unread by default
                }
            )
            notification.insert(ignore_permissions=True)

        # Success Response
        frappe.local.response.http_status_code = 200
        frappe.response["success"] = True
        frappe.response["message"] = "Notifications sent"

    except Exception as e:
        frappe.logger().error(f"Tata SmartFlow Webhook Error: {str(e)}")
        frappe.local.response.http_status_code = 500
        frappe.response["success"] = False
        frappe.response["message"] = f"Error processing webhook: {str(e)}"


def has_required_role(user, required_role):
    """Checks if the given user has the specified role."""
    user_roles = frappe.get_roles(user)  # Get all roles assigned to the user
    return required_role in user_roles  # Check if the required role exists
