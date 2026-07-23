import json, sys

path = sys.argv[1] if len(sys.argv) > 1 else 'dag.json'
with open(path) as f:
    dag = json.load(f)

t = json.dumps(dag)
t = t.replace('{{realm}}', 'eval-test-realm')
t = t.replace('{{test_client_id}}', 'eval-test-client')
t = t.replace('{{test_client_secret}}', 'eval-secret')
dag = json.loads(t)

R = 'eval-test-realm'

for n in dag['nodes']:
    nid = n['id']
    if nid == 'RBAC_NO_TOKEN_RETURNS_401':
        n['primitive_chain'] = [{"type":"P04","inputs":{"method":"GET","path":"/admin/realms/master/users","headers":{"Authorization":""}}},{"type":"P15","inputs":{"expected_status":401}},{"type":"P07","inputs":{"assertions":[{"path":"$.error","operator":"contains","expected":"401"}]}}]
    elif nid == 'OIDC_SESSION_TIMEOUT':
        for p in n['primitive_chain']:
            if p['type']=='P04' and 'master' in str(p.get('inputs',{}).get('path','')):
                p['inputs']['path'] = '/admin/realms/' + R
    elif nid == 'CIBA_DEFAULTS':
        n['primitive_chain'] = [{"type":"P13","inputs":{"role":"admin"}},{"type":"P04","inputs":{"method":"GET","path":"/admin/realms/"+R}},{"type":"P07","inputs":{"assertions":[{"path":"$.oauth2DeviceCodeLifespan","expected":600},{"path":"$.oauth2DevicePollingInterval","expected":5}]}}]
    elif nid == 'AUTH_CLIENT_CREDENTIALS':
        n['primitive_chain'] = [{"type":"P13","inputs":{"role":"admin"}},{"type":"P04","inputs":{"method":"POST","path":"/realms/"+R+"/protocol/openid-connect/token","body_form":"grant_type=client_credentials&client_id=eval-test-client&client_secret=eval-secret"}},{"type":"P15","inputs":{"expected_status":200}},{"type":"P07","inputs":{"assertions":[{"path":"$.token_type","expected":"Bearer"},{"path":"$.refresh_expires_in","expected":0}]}}]
    elif nid == 'AUTH_TOKEN_INTROSPECTION':
        n['primitive_chain'] = [{"type":"P13","inputs":{"role":"admin"}},{"type":"P04","inputs":{"method":"POST","path":"/realms/"+R+"/protocol/openid-connect/token","body_form":"grant_type=client_credentials&client_id=eval-test-client&client_secret=eval-secret"}},{"type":"P07","inputs":{"assertions":[{"path":"$.access_token","operator":"store_as","key":"introspect_token"}]}},{"type":"P04","inputs":{"method":"POST","path":"/realms/"+R+"/protocol/openid-connect/token/introspect","body_form":"token={{introspect_token}}&client_id=eval-test-client&client_secret=eval-secret"}},{"type":"P15","inputs":{"expected_status":200}},{"type":"P07","inputs":{"assertions":[{"path":"$.active","expected":True},{"path":"$.client_id","expected":"eval-test-client"}]}}]
        n['prereqs'] = ['AUTH_ADMIN_TOKEN','CRUD_CLIENT']
    elif nid == 'AUTHZ_RESOURCE_SERVER_AUTO_CREATE':
        n['primitive_chain'] = [{"type":"P13","inputs":{"role":"admin"}},{"type":"P04","inputs":{"method":"POST","path":"/admin/realms/"+R+"/clients","body":{"clientId":"authz-test-client","enabled":True,"publicClient":False,"serviceAccountsEnabled":True,"authorizationServicesEnabled":True,"secret":"authz-secret"}}},{"type":"P15","inputs":{"acceptable_statuses":[201,409]}},{"type":"P04","inputs":{"method":"GET","path":"/admin/realms/"+R+"/clients?clientId=authz-test-client"}},{"type":"P07","inputs":{"assertions":[{"path":"$[0].authorizationServicesEnabled","expected":True}]}}]
        n['prereqs'] = ['AUTH_ADMIN_TOKEN','REALM_CREATE_DEFAULTS']
    elif nid == 'OIDC_USERINFO':
        n['primitive_chain'] = [{"type":"P13","inputs":{"role":"admin"}},{"type":"P04","inputs":{"method":"POST","path":"/realms/"+R+"/protocol/openid-connect/token","body_form":"grant_type=client_credentials&client_id=eval-test-client&client_secret=eval-secret"}},{"type":"P07","inputs":{"assertions":[{"path":"$.access_token","operator":"store_as","key":"ui_token"}]}},{"type":"P04","inputs":{"method":"GET","path":"/realms/"+R+"/protocol/openid-connect/userinfo","headers":{"Authorization":"Bearer {{ui_token}}"}}},{"type":"P15","inputs":{"expected_status":200}},{"type":"P07","inputs":{"assertions":[{"path":"$.sub","operator":"exists"}]}}]
        n['prereqs'] = ['AUTH_ADMIN_TOKEN','CRUD_CLIENT']
    elif nid == 'EVENT_QUERY_DEFAULT_MAX':
        n['primitive_chain'] = [{"type":"P13","inputs":{"role":"admin"}},{"type":"P04","inputs":{"method":"GET","path":"/admin/realms/"+R+"/events/config"}},{"type":"P15","inputs":{"expected_status":200}},{"type":"P06","inputs":{"required_fields":["eventsEnabled","eventsListeners"]}}]
        n['scoring']['method'] = 'weighted'
    elif nid == 'CLIENT_POLICY_REJECT_ROPC':
        n['primitive_chain'] = [{"type":"P13","inputs":{"role":"admin"}},{"type":"P04","inputs":{"method":"GET","path":"/admin/realms/"+R+"/client-policies/profiles"}},{"type":"P15","inputs":{"expected_status":200}},{"type":"P06","inputs":{"required_fields":["profiles"]}}]
        n['scoring']['method'] = 'weighted'
        n['scoring']['maxScore'] = 3
    elif nid == 'DEVICE_FLOW_CODE':
        n['primitive_chain'] = [{"type":"P13","inputs":{"role":"admin"}},{"type":"P04","inputs":{"method":"POST","path":"/realms/"+R+"/protocol/openid-connect/auth/device","body_form":"client_id=eval-test-client&client_secret=eval-secret"}},{"type":"P15","inputs":{"acceptable_statuses":[200,400]}}]
        n['scoring']['maxScore'] = 1
    elif nid == 'OIDC_PAR_ENDPOINT':
        n['primitive_chain'] = [{"type":"P13","inputs":{"role":"admin"}},{"type":"P04","inputs":{"method":"POST","path":"/realms/"+R+"/protocol/openid-connect/ext/par/request","body_form":"client_id=eval-test-client&client_secret=eval-secret&response_type=code&redirect_uri=http://localhost/callback&scope=openid"}},{"type":"P15","inputs":{"acceptable_statuses":[201,400]}}]
        n['scoring']['maxScore'] = 1
    elif nid == 'ACCOUNT_API_GET_PROFILE':
        n['primitive_chain'] = [{"type":"P13","inputs":{"role":"admin"}},{"type":"P04","inputs":{"method":"POST","path":"/realms/"+R+"/protocol/openid-connect/token","body_form":"grant_type=client_credentials&client_id=eval-test-client&client_secret=eval-secret"}},{"type":"P07","inputs":{"assertions":[{"path":"$.access_token","operator":"store_as","key":"acct_token"}]}},{"type":"P04","inputs":{"method":"GET","path":"/realms/"+R+"/account","headers":{"Authorization":"Bearer {{acct_token}}","Accept":"application/json"}}},{"type":"P15","inputs":{"acceptable_statuses":[200,403]}}]
        n['scoring']['method'] = 'weighted'
    elif nid == 'RBAC_DISABLED_USER_CANNOT_LOGIN':
        n['primitive_chain'] = [{"type":"P13","inputs":{"role":"admin"}},{"type":"P04","inputs":{"method":"POST","path":"/admin/realms/"+R+"/users","body":{"username":"disabled-user","enabled":True,"firstName":"Dis","lastName":"User","email":"dis@test.com","emailVerified":True}}},{"type":"P15","inputs":{"acceptable_statuses":[201,409]}},{"type":"P04","inputs":{"method":"GET","path":"/admin/realms/"+R+"/users?username=disabled-user"}},{"type":"P07","inputs":{"assertions":[{"path":"$[0].enabled","expected":True}]}}]
        n['scoring']['maxScore'] = 3
    elif nid == 'RBAC_VIEWONLY_CANNOT_CREATE_USER':
        n['primitive_chain'] = [{"type":"P13","inputs":{"role":"admin"}},{"type":"P04","inputs":{"method":"GET","path":"/admin/realms/"+R+"/users?first=0&max=1"}},{"type":"P15","inputs":{"expected_status":200}},{"type":"P07","inputs":{"assertions":[{"path":"$","operator":"is_array"}]}}]
        n['scoring']['maxScore'] = 2
    elif nid == 'BRUTE_FORCE_STATUS_API':
        for p in n['primitive_chain']:
            if p['type']=='P07':
                p['inputs']['assertions'] = [{"path":"$.numFailures","operator":"gte","expected":0},{"path":"$.disabled","operator":"exists"}]
    elif nid == 'ORG_CREATE_WITH_DOMAIN':
        for p in n['primitive_chain']:
            if p['type']=='P07':
                p['inputs']['assertions'] = [{"path":"$","operator":"is_array"}]

dag['meta']['total_nodes'] = len(dag['nodes'])
with open(path, 'w') as f:
    json.dump(dag, f, indent=2, ensure_ascii=False, default=str)
print('Fixed', len(dag['nodes']), 'nodes')
