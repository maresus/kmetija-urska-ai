from app.services.chat_router import sessions, handle_message

session_id = 'test123'
sessions[session_id] = {'step': None, 'type': None, 'data': {}}

resp1 = handle_message('Rad bi rezerviral sobo', session_id)
print('1:', resp1[:150])
print('State:', sessions[session_id].get('step'))

resp2 = handle_message('15.1.2026', session_id)
print('2:', resp2[:150])
print('State:', sessions[session_id].get('step'))
