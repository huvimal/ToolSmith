from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import unittest
from domain import Store,PolicyError,ConflictError


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.temp.name)/'test.db')
    def tearDown(self):self.temp.cleanup()
    def propose(self,key='request_0001',now=None):
        return self.store.propose('ALPHA-001','in_progress','Review fixture',key,1,now)
    def approve(self,action,now=None):return self.store.review(action['action_id'],action['payload_sha256'],True,now)['receipt']

    def test_proposal_does_not_mutate_issue(self):
        self.propose()
        self.assertEqual(self.store.issue('ALPHA-001')['version'],1)
        self.assertEqual(self.store.events(),[])

    def test_pending_and_rejected_actions_cannot_apply(self):
        a=self.propose()
        with self.assertRaises(PolicyError):self.store.apply(a['action_id'],'no_receipt')
        self.store.review(a['action_id'],a['payload_sha256'],False)
        with self.assertRaises(PolicyError):self.store.apply(a['action_id'],'no_receipt')
        self.assertEqual(self.store.issue('ALPHA-001')['status'],'todo')

    def test_idempotency_key_binds_exact_payload(self):
        a=self.propose()
        self.assertEqual(a['action_id'],self.propose()['action_id'])
        with self.assertRaises(ConflictError):self.store.propose('ALPHA-001','in_progress','Different reason','request_0001',1)

    def test_exact_review_hash_and_receipt_required(self):
        a=self.propose()
        with self.assertRaises(ConflictError):self.store.review(a['action_id'],'0'*64,True)
        receipt=self.approve(a)
        with self.assertRaises(PolicyError):self.store.apply(a['action_id'],'wrong_token')
        self.assertEqual(self.store.apply(a['action_id'],receipt)['version'],2)

    def test_expired_approval_is_denied(self):
        a=self.propose(now=1000);receipt=self.approve(a,now=1001)
        with self.assertRaises(PolicyError):self.store.apply(a['action_id'],receipt,now=1600)
        self.assertEqual(self.store.issue('ALPHA-001')['version'],1)

    def test_stale_version_after_approval_is_a_conflict(self):
        a=self.propose();b=self.propose('request_0002')
        ra=self.approve(a);rb=self.approve(b)
        self.store.apply(a['action_id'],ra)
        with self.assertRaises(ConflictError):self.store.apply(b['action_id'],rb)
        self.assertEqual(len(self.store.events()),1)

    def test_concurrent_retries_commit_one_event(self):
        a=self.propose();receipt=self.approve(a)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda _:self.store.apply(a['action_id'],receipt),range(8)))
        self.assertEqual(sum(not r['replayed'] for r in results),1)
        self.assertEqual(self.store.issue('ALPHA-001')['version'],2)
        self.assertEqual(len(self.store.events()),1)

    def test_transaction_rolls_back_after_injected_post_update_failure(self):
        a=self.propose();receipt=self.approve(a)
        with self.store.connect() as db:
            db.execute("CREATE TRIGGER fail_result BEFORE UPDATE OF result ON actions BEGIN SELECT RAISE(ABORT,'fixture interruption'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.store.apply(a['action_id'],receipt)
        self.assertEqual(self.store.issue('ALPHA-001')['version'],1)
        self.assertEqual(self.store.events(),[])
        with self.store.connect() as db:db.execute('DROP TRIGGER fail_result')
        self.assertEqual(self.store.apply(a['action_id'],receipt)['version'],2)

    def test_cross_workspace_and_illegal_transition_denied(self):
        with self.assertRaises(PolicyError):self.store.issue('BETA-001')
        with self.assertRaises(PolicyError):self.store.propose('BETA-001','in_progress','bad','request_beta',1)
        with self.assertRaises(PolicyError):self.store.propose('ALPHA-001','done','Skip state','request_skip',1)

    def test_modified_payload_cannot_use_original_approval(self):
        a=self.propose();receipt=self.approve(a)
        with self.store.connect() as db:db.execute("UPDATE actions SET payload=replace(payload,'Review fixture','Tampered') WHERE id=?",(a['action_id'],))
        with self.assertRaises(ConflictError):self.store.apply(a['action_id'],receipt)

    def test_stale_or_expired_pending_proposal_can_still_be_rejected(self):
        stale=self.propose('request_stale',now=1000)
        live=self.propose('request_live',now=1000)
        receipt=self.approve(live,now=1001)
        self.store.apply(live['action_id'],receipt,now=1002)
        result=self.store.review(stale['action_id'],stale['payload_sha256'],False,now=2000)
        self.assertEqual(result['state'],'rejected')
        self.assertEqual(len(self.store.events()),1)
