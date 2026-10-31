import concurrent.futures
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('alert_receiver',Path(__file__).resolve().parents[1]/'deploy/k3s/operations/receiver.py')
receiver=importlib.util.module_from_spec(spec)
spec.loader.exec_module(receiver)


def payload(status='firing'):
    return {'status':status,'alerts':[{'status':status,'labels':{'alertname':'SGLangNoReadyWorker','namespace':'sglang-platform','severity':'critical','api_key':'DO_NOT_STORE'},'annotations':{'summary':'No Ready worker','description':'Inspect and rollback','password':'DO_NOT_STORE'},'startsAt':'2026-10-30T00:00:00Z','endsAt':''}]}


class AlertReceiverTests(unittest.TestCase):
    def setUp(self):
        receiver.EVENTS.clear();receiver.SEQUENCE=0

    def test_only_selected_fields_are_retained(self):
        receiver.store_payload(payload())
        self.assertNotIn('DO_NOT_STORE',str(list(receiver.EVENTS)))
        self.assertEqual(receiver.EVENTS[0]['alerts'][0]['labels']['alertname'],'SGLangNoReadyWorker')

    def test_firing_and_resolved_are_distinct_events(self):
        receiver.store_payload(payload());receiver.store_payload(payload('resolved'))
        self.assertEqual([x['status'] for x in receiver.EVENTS],['firing','resolved'])
        self.assertEqual([x['seq'] for x in receiver.EVENTS],[1,2])

    def test_invalid_envelope_cannot_add_an_event(self):
        with self.assertRaises(ValueError): receiver.store_payload({'status':'firing','alerts':'invalid'})
        self.assertEqual(len(receiver.EVENTS),0)

    def test_memory_is_bounded_with_monotonic_sequence(self):
        for _ in range(140): receiver.store_payload(payload())
        self.assertEqual(len(receiver.EVENTS),128)
        self.assertEqual(receiver.EVENTS[-1]['seq'],140)
        self.assertEqual(receiver.EVENTS[0]['seq'],13)

    def test_concurrent_delivery_preserves_sequence(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _:receiver.store_payload(payload()),range(64)))
        self.assertEqual(sorted(x['seq'] for x in receiver.EVENTS),list(range(1,65)))


if __name__=='__main__': unittest.main()
