# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
import datetime
import requests
from frappe.model.document import Document
from datetime import datetime, timedelta
from frappe.utils import get_url
from crm.integrations.api import get_contact_by_phone_number
from crm.utils import seconds_to_duration
from frappe.utils.background_jobs import enqueue
from frappe.utils.file_manager import save_file

# Pagination limit range for tatasmartflow
TIME_CHUNK_SECONDS = 2764799  # Equivalent to ~32 days
LOCK_KEYS = {
    "upload_recording": "upload_recordings_lock",
    "sync_call_log": "sync_call_log",
}


class CRMCallLog(Document):
    @staticmethod
    def default_list_data():
        columns = [
            {
                "key": "custom_tata_smart_flow_call_log_id",
                "type": "Data",
                "label": "Tata Smart Flow Call Log ID",
            },
            {
                "label": "Caller",
                "type": "Data",
                "key": "custom_crm_call_log_caller",
            },
            {
                "label": "Call Received By",
                "type": "Data",
                "key": "custom_call_received_by",
            },
            {"label": "Type", "type": "Select", "key": "custom_crm_call_log_type"},
            {"label": "Agent Name", "type": "Data", "key": "custom_agent_name"},
            {"label": "Service", "type": "Data", "key": "custom_service"},
            {"label": "Status", "type": "Select", "key": "custom_call_log_status"},
            {"label": "End Stamp", "type": "Select", "key": "custom_end_stamp"},
            {
                "label": "Call Duration (s)",
                "type": "Duration",
                "key": "custom_call_duration_s",
            },
        ]
        rows = [
            "custom_tata_smart_flow_call_log_id",
            "custom_crm_call_log_caller",
            "custom_call_received_by",
            "custom_crm_call_log_type",
            "custom_agent_name",
            "custom_service",
            "custom_call_log_status",
            "custom_end_stamp",
            "custom_call_duration_s",
        ]
        return {"columns": columns, "rows": rows}

    def has_link(self, doctype, name):
        for link in self.links:
            if link.link_doctype == doctype and link.link_name == name:
                return True

    def link_with_reference_doc(self, reference_doctype, reference_name):
        if self.has_link(reference_doctype, reference_name):
            return
        self.append(
            "links", {"link_doctype": reference_doctype, "link_name": reference_name}
        )


def parse_call_log(call):
    call["show_recording"] = False
    call["_duration"] = seconds_to_duration(call.get("duration"))

    if call.get("type") == "Incoming":
        call["activity_type"] = "incoming_call"
        contact = get_contact_by_phone_number(call.get("from"))
        receiver = (
            frappe.db.get_values(
                "User", call.get("custom_call_received_by"), ["full_name", "user_image"]
            )[0]
            if call.get("custom_call_received_by")
            else [None, None]
        )
        call["_caller"] = {
            "label": contact.get("full_name", "Unknown"),
            "image": contact.get("image"),
        }
        call["_receiver"] = {"label": receiver[0], "image": receiver[1]}

    elif call.get("type") == "Outgoing":
        call["activity_type"] = "outgoing_call"
        contact = get_contact_by_phone_number(call.get("to"))
        caller = (
            frappe.db.get_values(
                "User", call.get("caller"), ["full_name", "user_image"]
            )[0]
            if call.get("caller")
            else [None, None]
        )
        call["_caller"] = {"label": caller[0], "image": caller[1]}
        call["_receiver"] = {
            "label": contact.get("full_name", "Unknown"),
            "image": contact.get("image"),
        }

    return call


@frappe.whitelist()
def get_call_log(name):
    """Fetch a single call log directly from the CRM Call Log Doctype instead of using cache."""

    # Fields to exclude from the response
    excluded_fields = {
        "name",
        "creation",
        "modified",
        "modified_by",
        "owner",
        "docstatus",
        "idx",
        "telephony_medium",
        "id",
        "from",
        "duration",
        "medium",
        "start_time",
        "reference_doctype",
        "reference_docname",
        "to",
        "end_time",
        "note",
        "_user_tags",
        "_comments",
        "_assign",
        "_liked_by",
        "support_api_call",
        "voicemail_recording",
        "status",
        "type",
        "receiver",
        "caller",
        "recording_url",
        "custom_test",
    }

    # 🔎 Query the CRM Call Log Doctype for the specific call log
    call_log = frappe.db.get_value("CRM Call Log", {"name": name}, "*", as_dict=True)

    if call_log:
        # Remove excluded fields
        filtered_call_log = {
            key: value for key, value in call_log.items() if key not in excluded_fields
        }
        return filtered_call_log

    # If not found, return an error
    frappe.throw(f"Call log {name} not found. Please check the ID or refresh the list.")


def convert_to_datetime(datetime_str):
    """Convert a date-time string to a valid Frappe datetime format"""
    try:
        return datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def sync_tata_smartflow_logs():
    """Sync Tata Smartflow call logs incrementally or fully with second-based chunking."""

    # Check if lock is active
    LOCK_KEY = LOCK_KEYS.get("sync_call_log")

    if frappe.cache().get_value(LOCK_KEY):
        frappe.logger().info(
            "Another instance is running. Skipping sync_tata_smartflow_logs run."
        )
        return

    # Set the lock
    frappe.cache().set_value(LOCK_KEY, True, expires_in_sec=4 * 60 * 60)

    # Fetch settings from the single doctype 'Tata Smartflow Settings'
    settings = frappe.get_single("Tata Smartflow Settings")
    auth_token = settings.authentication_token.strip()
    api_url = settings.call_log_api_url.strip()
    sync_mode = settings.sync_mode.lower()  # 'full' or 'incremental'
    records_inserted = 0

    if not auth_token or not api_url:
        frappe.log_error("Missing API credentials", "Tata Smartflow API Sync")
        return

    headers = {"Authorization": auth_token, "Accept": "application/json"}

    try:
        # Step 1: Determine `from_date`
        if sync_mode == "incremental":
            latest_entry = frappe.db.sql(
                """
                SELECT CONCAT(custom_date, ' ', custom_time) AS latest_to_date
                FROM `tabCRM Call Log`
                ORDER BY latest_to_date DESC
                LIMIT 1
                """,
                as_dict=True,
            )
            # Extract and clean from_date safely
            from_date = None
            if latest_entry and latest_entry[0].get("latest_to_date"):
                latest_to_date = latest_entry[0]["latest_to_date"]
                from_date = (
                    latest_to_date.split(".")[0]
                    if "." in latest_to_date
                    else latest_to_date
                )
            if not from_date:
                frappe.msgprint("No previous logs found. Switching to full mode.")
                sync_mode = "full"

        if sync_mode == "full":
            # First available logs on Tata-Smartflow start from 2024-04-01 00:00:00
            from_date = "2024-04-01 00:00:00"

        # Step 2: Get latest `to_date` from API
        response = requests.get(
            api_url, headers=headers, params={"limit": 1, "page": 1}
        )
        response.raise_for_status()
        count_data = response.json()
        if not count_data.get("results"):
            frappe.msgprint("No call logs found in Tata Smartflow API.")
            return

        latest_entry = count_data["results"][0]
        to_date = f"{latest_entry.get('date', '')} {latest_entry.get('time', '')}"
        if not to_date.strip():
            frappe.log_error(
                "Failed to retrieve `to_date` for synchronization",
                "Tata Smartflow API Sync",
            )
            return

        # Step 3: Fetch in second-based chunks
        current_from_date = from_date
        max_limit = 1000  # API page size

        while current_from_date < to_date:
            current_to_date = (
                datetime.strptime(current_from_date, "%Y-%m-%d %H:%M:%S")
                + timedelta(seconds=TIME_CHUNK_SECONDS)
            ).strftime("%Y-%m-%d %H:%M:%S")

            # Ensure we don't exceed the actual `to_date`
            if current_to_date > to_date:
                current_to_date = to_date

            page = 1
            while True:
                params = {
                    "limit": max_limit,
                    "page": page,
                    "from_date": current_from_date,
                    "to_date": current_to_date,
                }

                response = requests.get(api_url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
                call_logs = data.get("results")

                if not call_logs:
                    break

                try:
                    for call in call_logs:
                        call_log_id = call.get("id")
                        direction = (
                            "Incoming"
                            if call.get("direction") == "inbound"
                            else "Outgoing"
                        )
                        agent_name = call.get("agent_name", "")
                        missed_agents = call.get("missed_agents", [])

                        if not agent_name:
                            agent_name = ", ".join(
                                missed_agent.get("name")
                                for missed_agent in missed_agents
                                if missed_agent.get("name")
                            )

                        audio_upload_status = (
                            "Not Started"
                            if call.get("answered_seconds") > 0
                            else "Not Required"
                        )

                        call_data = {
                            "doctype": "CRM Call Log",
                            "id": call_log_id,
                            "custom_tata_smart_flow_call_log_id": call_log_id,
                            "custom_call_id": call.get("call_id"),
                            "custom_uuid": call.get("uuid"),
                            "custom_direction": call.get("direction"),
                            "custom_description": call.get("description"),
                            "custom_detailed_description": call.get(
                                "detailed_description"
                            ),
                            "custom_call_log_status": call.get("status"),
                            "custom_blocked_number_id": call.get("blocked_number_id"),
                            "custom_external_recording_url": call.get("recording_url"),
                            "custom_service": call.get("service"),
                            "custom_date": call.get("date"),
                            "custom_time": call.get("time"),
                            "custom_end_stamp": call.get("end_stamp"),
                            "custom_broadcast_id": call.get("broadcast_id"),
                            "custom_dtmf_input": call.get("dtmf_input"),
                            "custom_call_duration_s": call.get("call_duration"),
                            "custom_answered_seconds": call.get("answered_seconds"),
                            "custom_minutes_consumed": call.get("minutes_consumed"),
                            "custom_charges": call.get("charges"),
                            "custom_department_name": call.get("department_name"),
                            "custom_agent_number": call.get("agent_number"),
                            "custom_agent_number_with_prefix": call.get(
                                "agent_number_with_prefix"
                            ),
                            "custom_agent_name": agent_name,
                            "custom_client_number": call.get("client_number"),
                            "custom_did_number": call.get("did_number"),
                            "custom_reason": call.get("reason"),
                            "custom_hangup_cause": call.get("hangup_cause"),
                            "custom_notes": frappe.as_json(call.get("notes") or {}),
                            "custom_contact_details": call.get("contact_details"),
                            "custom_missed_agents": frappe.as_json(
                                call.get("missed_agents") or {}
                            ),
                            "custom_agent_hangup_data": frappe.as_json(
                                call.get("agent_hangup_data") or {}
                            ),
                            "custom_call_tags": call.get("call_tags"),
                            "custom_account_id": call.get("accountid"),
                            "custom_agent_ring_time": safe_duration(
                                call.get("agent_ring_time")
                            ),
                            "custom_circle": frappe.as_json(call.get("circle") or {}),
                            "custom_transfer_missed_agent": frappe.as_json(
                                call.get("transfer_missed_agent") or {}
                            ),
                            "custom_call_flow": frappe.as_json(
                                call.get("call_flow") or {}
                            ),
                            "custom_call_hint": call.get("call_hint"),
                            "custom_lead_id": call.get("lead_id"),
                            "custom_sid": call.get("sid"),
                            "custom_sname": call.get("sname"),
                            "custom_is_incoming_from_broadcast": call.get(
                                "is_incoming_from_broadcast"
                            ),
                            "custom_caller_id_number": call.get("caller_id_num"),
                            "custom_sip_agent_ids": call.get("sip_agent_ids"),
                            "custom_dialer_call_details": call.get(
                                "dialer_call_details"
                            ),
                            "custom_custom_status": call.get("custom_status"),
                            "custom_is_whatsapp": call.get("is_whatsapp"),
                            "custom_aws_call_recording_identifier": call.get(
                                "aws_call_recording_identifier"
                            ),
                            "custom_crm_call_log_caller": (
                                call.get("client_number")
                                if direction == "Incoming"
                                else call.get("did_number")
                            ),
                            "custom_call_received_by": (
                                call.get("client_number")
                                if direction == "Outgoing"
                                else call.get("did_number")
                            ),
                            "custom_crm_call_log_type": direction,
                            "custom_call_log_status": (
                                "Completed"
                                if call.get("status") == "answered"
                                else (
                                    "No Answer"
                                    if call.get("status") == "missed"
                                    else "In Progress"
                                )
                            ),
                            "custom_audio_upload_status": audio_upload_status,
                        }

                        doc = frappe.get_doc(call_data)
                        doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
                        records_inserted += 1

                    frappe.db.commit()

                except Exception as error:
                    frappe.log_error(
                        "Tata Smartflow API Sync, internal try",
                        f"Error: {error}",
                    )
                    frappe.db.commit()

                # Move to next page
                page += 1
                frappe.db.commit()

            current_from_date = current_to_date  # Move to next chunk

        # Update the sync_mode (Set to 'full' or 'incremental')
        settings.sync_mode = "incremental"  # Change to "full" if needed

        # Save the changes
        settings.save()

        # Commit to database (if running in a script)
        frappe.db.commit()

        frappe.msgprint(
            f"Successfully synced {records_inserted} missing call logs up to {to_date}."
        )

    except requests.exceptions.RequestException as e:
        frappe.log_error(
            "Tata Smartflow API Sync",
            f"API Error: {str(e)}",
        )

    finally:
        # Release the lock manually
        frappe.cache().delete_value(LOCK_KEY)


def upload_recordings_for_answered_calls():
    # Check if lock is active
    LOCK_KEY = LOCK_KEYS.get("upload_recording")
    if frappe.cache().get_value(LOCK_KEY):
        frappe.logger().info(
            "Another instance is running. Skipping upload_recordings_for_answered_calls run."
        )
        print(" ching issue Not good".center(50, "-"))
        return

    # Set the lock
    frappe.cache().set_value(LOCK_KEY, True, expires_in_sec=24 * 60 * 60)

    # Fetch only logs where upload is required
    call_logs = frappe.get_all(
        "CRM Call Log",
        filters={
            "custom_audio_upload_status": ["in", ["Not Started", "Failed"]],
            "custom_answered_seconds": [">", 0],
        },
        fields=["name", "custom_external_recording_url"],
    )

    try:
        print(f"==>> call_logs: {len(call_logs)}")
        for log in call_logs:
            docname = log.name
            recording_url = log.custom_external_recording_url

            if not recording_url:
                frappe.logger().info(f"No recording URL for {docname}")
                frappe.db.set_value(
                    "CRM Call Log", docname, "custom_audio_upload_status", "Not Require"
                )
                continue

            # Download recording only if conditions are met
            response = requests.get(recording_url)

            if response.status_code != 200:
                print(f"==>> response.text: {response.text}")
                frappe.log_error(
                    f"Failed to download recording for {docname}",
                    f"from {recording_url}, Detail error: {response.text}",
                )
                frappe.db.set_value(
                    "CRM Call Log", docname, "custom_audio_upload_status", "Failed"
                )
                continue

            # Extract filename from URL or define it explicitly
            filename = f"{docname}_recording.mp3"

            try:
                # Save the file directly using Frappe's file manager
                file_doc = save_file(
                    fname=filename,
                    content=response.content,
                    dt="CRM Call Log",
                    dn=docname,
                    is_private=1,
                )

                # Update the CRM Call Log record with the file URL and status
                frappe.db.set_value(
                    "CRM Call Log",
                    docname,
                    {
                        "custom_audio_file": file_doc.file_url,
                        "custom_audio_upload_status": "Uploaded",
                    },
                )
                frappe.logger().info(f"Successfully uploaded recording for {docname}")

            except Exception as e:
                print(f"==>> e in tenral : {e}")
                frappe.db.set_value(
                    "CRM Call Log", docname, "custom_audio_upload_status", "Failed"
                )
                frappe.log_error(f"Upload failed for {docname}:", str(e))

    except Exception as e:
        print(f"==>> e: {e}")
        frappe.log_error(f"Error processing {docname}:", str(e))
        frappe.db.set_value(
            "CRM Call Log", docname, "custom_audio_upload_status", "Failed"
        )
    finally:
        # Release the lock manually
        frappe.db.commit()
        frappe.cache().delete_value(LOCK_KEY)


def safe_duration(value):
    return None if value in ["N.A.", None, ""] else float(value)


@frappe.whitelist()
def enqueue_fetch_tata_smartflow_logs():
    """Enqueue the sync function to run in the background with 4 hour timeout"""
    enqueue(
        sync_tata_smartflow_logs, queue="default", timeout=14400
    )  # 4 hour (14400 seconds)


@frappe.whitelist()
def enqueue_upload_call_logs_recondings():
    """Enqueue the sync function to run in the background with 1 day timeout"""
    enqueue(
        upload_recordings_for_answered_calls, queue="default", timeout=86400
    )  # 1 day (86400 seconds)
