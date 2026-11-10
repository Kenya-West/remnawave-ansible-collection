# -*- coding: utf-8 -*-
# Copyright (c) 2026, Kenya-West <Kenya-West@outlook.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Squad/template planning and named response rule tests."""

import unittest

from ansible_collections.kenyawest.remnawave.plugins.module_utils.squad import (
    apply_entity, entity_options, plan_entity, run_batch,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.response_rule import (
    plan_response_rules, response_rule_options,
)
from ansible_collections.kenyawest.remnawave.plugins.module_utils.client import RemnawaveApiError, RemnawaveClient

UUID = '11111111-1111-1111-1111-111111111111'


class Module:
    check_mode = False
    _diff = True

    def fail_json(self, **kwargs):
        raise ValueError(kwargs['msg'])


class Client:
    def __init__(self):
        self.writes = []
        self.data = {
            '/api/internal-squads': {'internalSquads': [dict(uuid=UUID, name='internal', tags=['PAID'], inbounds=[{'uuid': 'ib'}])]},
            '/api/external-squads': {'externalSquads': [
                dict(uuid=UUID, name='external', tags=[], templates=[],
                     subscriptionSettings={'randomizeHosts': True, 'isShowCustomRemarks': True},
                     hwidSettings={'enabled': True}, responseHeadersRemove=[])]},
            '/api/subscription-templates': {'templates': [dict(uuid=UUID, name='json-template', templateType='XRAY_JSON', templateJson=None, tags=[])]},
            '/api/subscription-templates/' + UUID: dict(uuid=UUID, name='json-template', templateType='XRAY_JSON', templateJson={'outbounds': []}, tags=[]),
        }

    def get(self, path, cached=False):
        return self.data[path]

    def post(self, path, data):
        self.writes.append(('POST', path, data))
        return dict(data, uuid=UUID)

    def patch(self, path, data):
        self.writes.append(('PATCH', path, data))
        return data

    def delete(self, path):
        self.writes.append(('DELETE', path, None))


def params(kind, **values):
    options = response_rule_options() if kind == 'rule' else entity_options(kind)
    result = {k: v.get('default') for k, v in options.items()}
    result.update(values)
    return result


class TestSquadTemplates(unittest.TestCase):
    def test_omitted_fields_are_untouched(self):
        for kind, name in [('internal_squad', 'internal'), ('external_squad', 'external'),
                           ('subscription_template', 'json-template')]:
            self.assertEqual(plan_entity(Module(), Client(), kind, params(kind, name=name))['action'], 'none')

    def test_template_content_is_read_from_detail_not_listing(self):
        plan = plan_entity(Module(), Client(), 'subscription_template', params('subscription_template', name='json-template', template_json={'outbounds': []}))
        self.assertEqual(plan['action'], 'none')

    def test_external_nested_options_preserve_omitted_suboptions(self):
        plan = plan_entity(Module(), Client(), 'external_squad', params('external_squad', name='external', subscription_settings={'randomize_hosts': False}))
        self.assertEqual(plan['payload'], {'subscriptionSettings': {'randomizeHosts': False, 'isShowCustomRemarks': True}})

    def test_external_templates_resolve_by_name(self):
        plan = plan_entity(Module(), Client(), 'external_squad', params('external_squad', name='external', templates=['json-template']))
        self.assertEqual(plan['payload']['templates'], [{'templateUuid': UUID, 'templateType': 'XRAY_JSON'}])
        with self.assertRaisesRegex(ValueError, 'one subscription template per type'):
            plan_entity(Module(), Client(), 'external_squad', params('external_squad', name='external', templates=['json-template', UUID]))

    def test_external_unknown_template_fails_except_in_check_mode(self):
        p = params('external_squad', name='external', templates=['future'])
        with self.assertRaises(RemnawaveApiError):
            plan_entity(Module(), Client(), 'external_squad', p)
        module = Module()
        module.check_mode = True
        self.assertEqual(plan_entity(module, Client(), 'external_squad', p)['payload']['templates'][0]['templateUuid'], 'future')

    def test_json_null_clears_override(self):
        p = plan_entity(Module(), Client(), 'external_squad', params('external_squad', name='external', hwid_settings='null'))
        self.assertEqual(p['payload'], {'hwidSettings': None})

    def test_template_type_is_immutable(self):
        with self.assertRaisesRegex(ValueError, 'cannot be changed'):
            plan_entity(Module(), Client(), 'subscription_template', params('subscription_template', name='json-template', template_type='MIHOMO'))

    def test_template_creation_uses_followup_content_and_tags(self):
        client = Client()
        p = plan_entity(Module(), client, 'subscription_template', params(
            'subscription_template', name='new-template', template_type='MIHOMO',
            template_yaml='proxies: []\n', tags=['PAID']))
        apply_entity(Module(), client, p)
        self.assertEqual(client.writes, [
            ('POST', '/api/subscription-templates', {'name': 'new-template', 'templateType': 'MIHOMO'}),
            ('PATCH', '/api/subscription-templates', {'uuid': UUID, 'encodedTemplateYaml': 'cHJveGllczogW10K'}),
            ('PATCH', '/api/subscription-templates/tags', {'uuid': UUID, 'tags': ['PAID']})])

    def test_empty_nested_options_do_not_create_overrides(self):
        client = Client()
        client.data['/api/external-squads']['externalSquads'][0]['hostOverrides'] = None
        p = plan_entity(Module(), client, 'external_squad', params(
            'external_squad', name='external', host_overrides={}))
        self.assertEqual(p['action'], 'none')

    def test_invalid_condition_is_refused_without_mutation(self):
        current = TestResponseRules().current()
        with self.assertRaisesRegex(ValueError, 'invalid HTTP header'):
            plan_response_rules(Module(), current, [params('rule', name='first', conditions=[dict(
                header_name='invalid header', operator='EQUALS', value='value', case_sensitive=False)])])
        self.assertEqual(current['responseRules']['rules'][0]['conditions'], [])

    def test_check_mode_does_not_write(self):
        module, client = Module(), Client()
        module.check_mode = True
        plan = plan_entity(module, client, 'internal_squad', params('internal_squad', name='internal', tags=[]))
        result = apply_entity(module, client, plan)
        self.assertTrue(result['changed'])
        self.assertEqual(result['squad']['tags'], [])
        self.assertEqual(client.writes, [])

    def test_required_create_fields_and_name_validation(self):
        for kind in ['internal_squad', 'subscription_template']:
            with self.assertRaisesRegex(ValueError, 'required when creating'):
                plan_entity(Module(), Client(), kind, params(kind, name='new'))
        with self.assertRaisesRegex(ValueError, '2 to 30'):
            plan_entity(Module(), Client(), 'external_squad', params('external_squad', name='x'))


class Exit(Exception):
    def __init__(self, result):
        self.result = result


class BatchModule(Module):
    def exit_json(self, **kwargs):
        raise Exit(kwargs)

    def fail_json(self, **kwargs):
        raise Exit(dict(kwargs, failed=True))


class BatchClient(Client):
    run_parallel = staticmethod(RemnawaveClient.run_parallel)

    def __init__(self, reject=None):
        super().__init__()
        self.reject = reject

    def prefetch(self, paths):
        for path in paths:
            self.get(path, cached=True)

    def patch(self, path, data):
        if path == self.reject:
            raise RemnawaveApiError('rejected', status=400)
        return super().patch(path, data)

    def post(self, path, data):
        result = super().post(path, data)
        if path == '/api/external-squads':
            self.data[path]['externalSquads'].append(dict(result, tags=[], viewPosition=1))
        return result


class TestBatches(unittest.TestCase):
    def execute(self, entries, client=None, check=False):
        module = BatchModule()
        module.check_mode = check
        module.params = dict(squads=entries, parallelism=1, order=False)
        client = client or BatchClient()
        with self.assertRaises(Exit) as exc:
            run_batch(module, client, 'external_squad')
        return exc.exception.result, client

    def test_duplicate_name_and_uuid_fails_before_any_writes(self):
        result, client = self.execute([
            params('external_squad', name='external', tags=['CHANGED']),
            params('external_squad', name=UUID)])
        self.assertTrue(result['failed'])
        self.assertEqual(client.writes, [])
        self.assertIn('Nothing was changed', result['msg'])

    def test_invalid_later_entry_fails_before_any_writes(self):
        result, client = self.execute([
            params('external_squad', name='external', tags=['CHANGED']),
            params('external_squad', name='valid-name', tags=['invalid'])])
        self.assertTrue(result['failed'])
        self.assertEqual(client.writes, [])

    def test_check_mode_predicts_each_entry_without_writes(self):
        result, client = self.execute([
            params('external_squad', name='external', tags=['CHANGED']),
            params('external_squad', name='new-squad')], check=True)
        self.assertEqual([r['action'] for r in result['results']], ['update', 'create'])
        self.assertEqual(client.writes, [])

    def test_rejected_update_stops_creation_step_and_reports_no_changes(self):
        result, client = self.execute([
            params('external_squad', name='external', tags=['CHANGED']),
            params('external_squad', name='new-squad')],
            client=BatchClient(reject='/api/external-squads/tags'))
        self.assertTrue(result['failed'])
        self.assertFalse(result['changed'])
        self.assertEqual(client.writes, [])

    def test_rejected_followup_reports_prior_creation_as_changed(self):
        result, client = self.execute([params('external_squad', name='new-squad', tags=['PAID'])],
                                      client=BatchClient(reject='/api/external-squads/tags'))
        self.assertTrue(result['failed'])
        self.assertTrue(result['changed'])
        self.assertEqual(result['results'], [])
        self.assertEqual(client.writes[0][0], 'POST')


class TestResponseRules(unittest.TestCase):
    def current(self):
        return {'uuid': UUID, 'responseRules': {'version': '1', 'settings': {'disableSubscriptionAccessByPath': True}, 'rules': [
            dict(name='first', enabled=False, operator='AND', conditions=[], responseType='BLOCK'),
            dict(name='unmanaged', enabled=True, operator='AND', conditions=[], responseType='BROWSER'),
            dict(name='last', enabled=True, operator='AND', conditions=[], responseType='MIHOMO')]}}

    def test_present_preserves_disabled_and_unmanaged_rules(self):
        current = self.current()
        config, results, changed = plan_response_rules(Module(), current, [params('rule', name='first')])
        self.assertFalse(changed)
        self.assertEqual(config, current['responseRules'])
        self.assertFalse(results[0]['rule']['enabled'])

    def test_enable_and_authoritative_conditions(self):
        entry = params('rule', name='first', state='enabled', conditions=[dict(
            header_name='user-agent', operator='CONTAINS', value='Happ', case_sensitive=True)])
        config, results, changed = plan_response_rules(Module(), self.current(), [entry])
        self.assertTrue(changed)
        self.assertEqual(config['rules'][0]['conditions'], [dict(headerName='user-agent', operator='CONTAINS', value='Happ', caseSensitive=True)])
        self.assertTrue(config['rules'][0]['enabled'])
        self.assertTrue(config['settings']['disableSubscriptionAccessByPath'])
        self.assertEqual(results[0]['action'], 'update')

    def test_create_defaults_and_idempotency(self):
        entry = params('rule', name='new', response_type='BLOCK')
        config, results, changed = plan_response_rules(Module(), {}, [entry])
        self.assertEqual(config['rules'][0], dict(name='new', responseType='BLOCK', operator='AND', conditions=[], enabled=True))
        self.assertFalse(plan_response_rules(Module(), {'responseRules': config}, [entry])[2])

    def test_delete_and_missing_delete(self):
        config, results, changed = plan_response_rules(Module(), self.current(), [params('rule', name='first', state='absent')])
        self.assertEqual([r['name'] for r in config['rules']], ['unmanaged', 'last'])
        self.assertTrue(changed)
        self.assertFalse(plan_response_rules(Module(), {}, [params('rule', name='missing', state='absent')])[2])

    def test_order_preserves_unlisted_slot(self):
        entries = [params('rule', name='last'), params('rule', name='first')]
        config, results, changed = plan_response_rules(Module(), self.current(), entries, order=True)
        self.assertEqual([r['name'] for r in config['rules']], ['last', 'unmanaged', 'first'])
        self.assertTrue(all(r['changed'] for r in results))
        self.assertFalse(plan_response_rules(Module(), {'responseRules': config}, entries, order=True)[2])

    def test_prevalidation_does_not_mutate_current(self):
        current = self.current()
        with self.assertRaisesRegex(ValueError, 'required when creating'):
            plan_response_rules(Module(), current, [params('rule', name='first', state='absent'), params('rule', name='new')])
        self.assertEqual(len(current['responseRules']['rules']), 3)
        with self.assertRaisesRegex(ValueError, 'declared twice'):
            plan_response_rules(Module(), current, [params('rule', name='first'), params('rule', name='first')])


if __name__ == '__main__':
    unittest.main()
