from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import matter_store


class ApiV08SmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_db_path = matter_store.DB_PATH
        matter_store.DB_PATH = Path(self.tempdir.name) / "caseops_test.db"
        sys.modules.pop("api_server", None)
        self.api_server = importlib.import_module("api_server")
        self.client = TestClient(self.api_server.app)
        self.headers = {"X-API-Key": "demo-key"}

    def tearDown(self) -> None:
        sys.modules.pop("api_server", None)
        matter_store.DB_PATH = self.original_db_path
        self.tempdir.cleanup()

    def test_health_and_auth_contract(self) -> None:
        health = self.client.get("/v1/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json(), {"status": "ok", "version": "0.8.0"})

        missing_key = self.client.get("/v1/matters")
        self.assertEqual(missing_key.status_code, 401)
        self.assertEqual(missing_key.json()["error"], "unauthorized")

        matters = self.client.get("/v1/matters", headers=self.headers)
        self.assertEqual(matters.status_code, 200)
        self.assertIn("MAT-1001", {matter["matter_id"] for matter in matters.json()})

    def test_approve_requires_valid_action_fields(self) -> None:
        response = self.client.post(
            "/v1/actions/approve",
            headers=self.headers,
            json={"approved_action": {"action_type": "create_task", "matter_id": "MAT-1001"}},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "action_validation_error")

        calendar_response = self.client.post(
            "/v1/actions/approve",
            headers=self.headers,
            json={
                "approved_action": {
                    "action_type": "create_calendar_event",
                    "matter_id": "MAT-1001",
                    "title": "Mediation prep",
                    "event_date": "tomorrow",
                }
            },
        )
        self.assertEqual(calendar_response.status_code, 400)
        self.assertEqual(calendar_response.json()["error"], "action_validation_error")

    def test_idempotent_approval_tasks_and_webhooks(self) -> None:
        payload = {
            "approved_action": {
                "action_type": "create_task",
                "matter_id": "MAT-1001",
                "title": "Request PT records",
                "assigned_to": "Miguel Santos",
                "due_date": None,
                "reason": "Mini LOIS identified missing PT records after April 19.",
            },
            "source_refs": ["S1", "S2"],
        }
        headers = {**self.headers, "Idempotency-Key": "approve-test-001"}

        first = self.client.post("/v1/actions/approve", headers=headers, json=payload)
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.json()["idempotency"]["replayed"])

        second = self.client.post("/v1/actions/approve", headers=headers, json=payload)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["idempotency"]["replayed"])

        tasks = self.client.get("/v1/matters/MAT-1001/tasks?status=Open", headers=self.headers)
        self.assertEqual(tasks.status_code, 200)
        self.assertEqual([task["title"] for task in tasks.json()].count("Request PT records"), 1)

        webhooks = self.client.get(
            "/v1/matters/MAT-1001/webhook-events?event_type=task.created",
            headers=self.headers,
        )
        self.assertEqual(webhooks.status_code, 200)
        self.assertEqual(len(webhooks.json()), 1)
        self.assertEqual(webhooks.json()[0]["payload"]["source_refs"], ["S1", "S2"])

    def test_databridge_import_create_then_update(self) -> None:
        payload = {
            "external_system": "demo_crm",
            "external_case_id": "ABC-123",
            "client_full_name": "Alicia Johnson",
            "case_type": "Personal Injury",
            "matter_name": "Johnson v. RideshareCo Imported",
            "phase": "Imported intake",
            "lead_attorney": "Dana Cruz",
            "paralegal": "Miguel Santos",
        }
        created = self.client.post("/v1/databridge/import", headers=self.headers, json=payload)
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["status"], "created")
        self.assertEqual(created.json()["matter"]["matter_id"], "MAT-EXT-ABC-123")

        updated_payload = {**payload, "phase": "Updated intake"}
        updated = self.client.post("/v1/databridge/import", headers=self.headers, json=updated_payload)
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["status"], "updated")
        self.assertEqual(updated.json()["matter"]["phase"], "Updated intake")


if __name__ == "__main__":
    unittest.main()
