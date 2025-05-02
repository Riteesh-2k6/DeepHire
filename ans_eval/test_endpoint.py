import requests
import json

def test_evaluate_endpoint():
    try:
        url = 'http://127.0.0.1:8000/evaluate'
        files = {'file': ('test_interview.json', open('test_interview.json', 'rb'), 'application/json')}
        
        print('Sending request to evaluate endpoint...')
        response = requests.post(url, files=files)
        print(f'Status Code: {response.status_code}')
        print(f'Response: {response.text}')
        
        if response.status_code == 500:
            print('\nServer Error Details:')
            error_data = response.json()
            print(f'Error Message: {error_data.get("message", "No error message provided")}')
    except requests.exceptions.ConnectionError:
        print('Error: Could not connect to the server. Make sure Flask is running.')
    except Exception as e:
        print(f'Error: {str(e)}')

if __name__ == '__main__':
    test_evaluate_endpoint()