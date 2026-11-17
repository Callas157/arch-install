import unittest
from callas_chat.protocol import JsonLines, thread_params, turn_params, messages_from_thread


class ProtocolTests(unittest.TestCase):
    def test_partial_utf8_and_multiple_events(self):
        parser = JsonLines()
        raw = '{"text":"ação"}\n{"id":2}\n'.encode()
        cut = raw.index('ç'.encode()) + 1
        self.assertEqual(parser.feed(raw[:cut]), [])
        self.assertEqual(parser.feed(raw[cut:]), [{'text': 'ação'}, {'id': 2}])

    def test_malformed_line_is_an_explicit_error(self):
        with self.assertRaises(ValueError):
            JsonLines().feed(b'not-json\n')

    def test_full_access_on_start_resume_and_each_turn(self):
        params = thread_params('/home/test')
        self.assertEqual(params['approvalPolicy'], 'never')
        self.assertEqual(params['sandbox'], 'danger-full-access')
        turn = turn_params('conversation', 'Olá', '/home/test')
        self.assertEqual(turn['approvalPolicy'], 'never')
        self.assertEqual(turn['sandboxPolicy'], {'type': 'dangerFullAccess'})
        self.assertEqual(turn['input'], [{'type': 'text', 'text': 'Olá'}])

    def test_history_keeps_roles_and_ignores_hidden_reasoning(self):
        thread = {'turns': [{'items': [
            {'id': 'u', 'type': 'userMessage', 'content': [{'type': 'text', 'text': 'Olá'}]},
            {'id': 'r', 'type': 'reasoning', 'text': 'hidden'},
            {'id': 'a', 'type': 'agentMessage', 'text': '**Olá!**'},
            {'id': 'c', 'type': 'commandExecution', 'command': 'pwd', 'aggregatedOutput': '/home/test'},
        ]}]}
        messages = messages_from_thread(thread)
        self.assertEqual([m['role'] for m in messages], ['user', 'assistant', 'tool'])
        self.assertEqual(messages[2]['text'], 'pwd\n\n/home/test')

    def test_history_extracts_multiple_document_cards_without_exposing_contents(self):
        prompt = 'Confira os arquivos'
        paths = ['/tmp/Arquivo de texto.txt', '/tmp/registro.log']
        for path in paths:
            prompt += '\n\nArquivo anexado: ' + path + '\n<conteudo_do_arquivo>\nconteúdo\n</conteudo_do_arquivo>'
        thread = {'turns': [{'items': [{'id': 'u', 'type': 'userMessage',
                   'content': [{'type': 'text', 'text': prompt}]}]}]}
        message = messages_from_thread(thread)[0]
        self.assertEqual(message['text'], 'Confira os arquivos')
        self.assertEqual(message['documents'], paths)

    def test_external_images_are_not_loaded_as_html(self):
        from callas_chat.protocol import safe_markdown
        self.assertNotIn('<img', safe_markdown('<img src="https://example.org/x">'))
        self.assertNotIn('https://example.org/x', safe_markdown('![foto](https://example.org/x)'))


if __name__ == '__main__':
    unittest.main()


class ImageHistoryTests(unittest.TestCase):
    def test_image_only_message_keeps_local_photo(self):
        thread = {'turns': [{'items': [{'id': 'photo', 'type': 'userMessage',
                  'content': [{'type': 'localImage', 'path': '/tmp/photo.png'}]}]}]}
        messages = messages_from_thread(thread)
        self.assertEqual(messages[0]['images'], ['/tmp/photo.png'])
        self.assertEqual(messages[0]['text'], '')
