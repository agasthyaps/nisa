from flask import Flask, render_template, Response, jsonify, request, redirect, url_for
from flask_socketio import SocketIO
# from dotenv import load_dotenv
import logging
from threading import Event
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
    Microphone,
)
from convo_tools import conversation_engine, create_coach_with_context
import json
import sounddevice as sd
import threading
# from queue import Queue
from enum import Enum, auto

app = Flask(__name__)
socketio = SocketIO(app)

class State(Enum):
    IDLE = auto()
    WAITING_FOR_LLM_RESPONSE = auto()
    # HANDLING_LLM_RESPONSE = auto()
    LISTENING = auto()
    PROCESSING_USER_SPEECH = auto()
    SENDING_TO_DOM = auto()

# Initially, the system is IDLE
current_state = State.IDLE

# Set up client configuration
config = DeepgramClientOptions(
    # options={"keepalive": "true"}
)

# Initialize Deepgram client and connection
deepgram = DeepgramClient("",config)
dg_connection = deepgram.listen.live.v("1")
# dg_connection_open = False

# Initialize coach
coach = None
ridealong = None
full_transcript = []
user = None

# Track transcription state
# transcribing = False
# transcription_event = Event()
# should_restart = False

# track whether we are practicing or not
practicing = False

def configure_deepgram():
    global practicing
    global dg_connection
    # global dg_connection_open
    if practicing:
        options = LiveOptions(
            smart_format=True,
            language="en-US",
            encoding="linear16",
            channels=1,
            sample_rate=16000,
            interim_results=True,
            utterance_end_ms="10000",
            vad_events=True,
        )
    else:
        options = LiveOptions(
            smart_format=True,
            language="en-US",
            encoding="linear16",
            channels=1,
            sample_rate=16000,
            punctuate = True,
            interim_results=True,
            utterance_end_ms="3000",
            vad_events=True,
        )
    dg_connection.start(options)
    # dg_connection_open = True
    # print(dg_connection)
    print("Deepgram connection started.")

def start_microphone():
    global dg_connection
    microphone = Microphone(dg_connection.send)
    microphone.start()
    print("Microphone started.")
    return microphone

convo_round =0

def start_practice():
    global practicing
    practicing = True
    listen()

def end_practice():
    global practicing
    global transcribing
    # global transcription_event
    practicing = False
    # transcribing = False
    # transcription_event.set()
    listen()

def speak(message):
    print("speak was called")
    return

def alert_coach():
    global coach
    global full_transcript
    global user
    alert_message = """
    your assistant has noticed something the teacher just said that warrants a redirect.
    review the transcript and your thinking plan to determine what feedback to give.

    teacher practice up until now: {}
    """.format(full_transcript[-1])

    socketio.emit('chat_response', {'sender':'user','message': user + full_transcript[-1]}) 
    response = conversation_engine(coach, alert_message)
    response = json.loads(response)
    handle_llm_response(response) 

def end_session():
    global dg_connection
    # stop_transcribing()
    dg_connection.finish()
    return

def handle_llm_response(response):
    global current_state
    if current_state == State.WAITING_FOR_LLM_RESPONSE:
        global full_transcript
        thread_name = threading.current_thread().name
        message = response['message']
        action = response['action']

        full_transcript.append(message)
        speak(message)
        socketio.emit('chat_response', {'sender': 'nisa', 'message': 'nisa: ' + message})
        print(f"{thread_name} SENDING TO DOM: {message} ")

        action_map = {
            'listen to user': [listen, State.LISTENING],
            'start practice': [start_practice, State.LISTENING],
            'end practice': [end_practice, State.LISTENING],
            'alert coach': [alert_coach, State.PROCESSING_USER_SPEECH],
            'end session': [end_session, State.IDLE]
        }
        if action in action_map:
            action_function, next_state = action_map[action]
            print(f"{thread_name} says action is {action}, about to execute action and change state to {next_state}")

            current_state = next_state
            action_function()
        else:
            current_state = State.IDLE
    else:
        print(f"not time for HANDLE_LLM_RESPONSE, current state is {current_state}.")

def process_conversation(user_message):
    global current_state
    if current_state == State.PROCESSING_USER_SPEECH:
        global coach

        thread_name = threading.current_thread().name
        current_state = State.WAITING_FOR_LLM_RESPONSE

        response = conversation_engine(coach, user_message)
        response = json.loads(response)

        print(f"{thread_name} says coach said: {response['message']}, about to send to handle_llm_response.")
        handle_llm_response(response)
    else:
        print(f"not time for PROCESS_CONVERSATION, current state is {current_state}.")

    # action_queue.put(handle_llm_response(response))


last_message = ""
listener_attached = False

def listen():
    global current_state
    if current_state == State.LISTENING:
        global dg_connection, listener_attached
        interim_transcript = ""
        is_finals = []

        if listener_attached:
            print("closing old connection")
            dg_connection.finish() # we turned keepAlive on so we can just finish and start a new connection
            listener_attached = False

        print("top of listen")
        
        # collect interim transcripts
        def on_message(self, result, **kwargs):
            global current_state, last_message
            nonlocal is_finals
            nonlocal interim_transcript

            print("data recieved")

            transcript = result.channel.alternatives[0].transcript
            if not transcript:
                return
            if result.is_final:
                print(f"is_final and conversation")
                is_finals.append(transcript)
                if result.speech_final:
                    print(f"speech_final and conversation")
                    user_message = ' '.join(is_finals)
                    if user_message == interim_transcript:
                        print(f"duplicate messages. last message: {interim_transcript}, current message: {user_message}")
                        return
                    interim_transcript = user_message
            
        # let's just be thorough and make sure we're not sending the same message twice. wait for the utterance end flag
        def on_utterance_end(self, utterance_end, **kwargs):
            global current_state

            print("ok here we go")
            final_message = ' '.join(is_finals)
            if final_message == interim_transcript:
                final_message = interim_transcript
                print(f"User said this, sending it to process: {final_message}")
                is_finals = []
                socketio.emit('chat_response', {'sender': 'user', 'message': user + ': ' + final_message})
                print(f"just sent user message {final_message} to DOM.")
                current_state = State.PROCESSING_USER_SPEECH
                process_conversation(final_message)  

        try:
            print(f"Starting transcription loop and last message was {last_message}!")
            dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
            dg_connection.on(LiveTranscriptionEvents.UtteranceEnd, on_utterance_end)
            configure_deepgram()
            listener_attached = True
            microphone = start_microphone()
            print("Listening...")
            socketio.emit('ui_flag', {'sender':'ui_flag', 'message': '(nisa is listening to you...)'})

        except Exception as e:
            logging.error(f"Error in listen: {e}")

        finally:
            if dg_connection:
                dg_connection.finish()
                listener_attached = False
            if microphone:
                microphone.finish()

def reconnect():
    try:
        print("Reconnecting to Deepgram...")
        new_dg_connection = deepgram.listen.live.v("1")

        # Configure and start the new Deepgram connection
        configure_deepgram(new_dg_connection)

        print("Reconnected to Deepgram successfully.")
        return new_dg_connection

    except Exception as e:
        logging.error(f"Reconnection failed: {e}")
        return None

def on_disconnect():
    print("Client disconnected")
    global dg_connection
    if dg_connection:
        dg_connection.finish()
        dg_connection = None
        print("Cleared listeners and set dg_connection to None")
    else:
        print("No active dg_connection to disconnect from")

@app.route('/')
def login():
    return render_template('login.html')

@app.route('/start_session', methods=['POST'])
def start_session():
    global coach

    user_name = request.form['user_name']
    scenario = "explain the concept of ratios to 6th graders." # get this from a database or something using user as key
    coach = create_coach_with_context("gpt", scenario,user_name) # 'gpt'= gpt 4 turbo; 'llama' = llama 3 70b via Groq; 'haiku' = claude haiku

    return redirect(url_for('index', user=user_name))

@app.route('/index')
def index():
    global user
    user_name = request.args.get('user', 'Guest')
    user = user_name
    return render_template('index.html', user_name=user_name)

@socketio.on('request_initial_message')
def handle_initial_message():
    global current_state
    print(f"Received 'request_initial_message' event from client with SID: {request.sid}")
    current_state = State.PROCESSING_USER_SPEECH
    process_conversation("begin session. do not acknowledge receipt of this message.")

@socketio.on('disconnect')
def handle_disconnect():
    socketio.start_background_task(target=on_disconnect)

if __name__ == '__main__':
    print("Starting SocketIO server.")
    socketio.run(app, debug=True)

######################MORTUARY###########################
# Below is the original listen function
# def listen():
#     print("listen was called")
#     global transcribing, dg_connection, transcription_event

#     if transcribing:
#         print("Transcription is already active. No need to start again.")
#         return
#     else:
#         start_transcribing() # transcribing = True, transcription_event.clear()

#     running_transcript = ""  
#     microphone = None

#     try:
#         configure_deepgram()
#         microphone = start_microphone()
#         print("listening")

#         while transcribing:
#             def on_message(self, result, **kwargs):
#                 global transcribing, full_transcript, coach, ridealong, practicing, user, transcription_event
#                 nonlocal running_transcript
#                 batch_size = 125

#                 transcript = result.channel.alternatives[0].transcript
#                 if transcript:
#                     print(transcript)
#                 else:
#                     print("nothing yet")
#                 running_transcript += transcript

#                 if not practicing:
#                     if result.is_final and result.speech_final:
#                         print("final utterance, need to stop listening")
#                         print("user said:", running_transcript)
#                         stop_transcribing() # transcribing = False, transcription_event.set()

#                         full_transcript.append(running_transcript)
#                         socketio.emit('chat_response', {'sender':'user','message': user + ': ' + running_transcript})
                        
#                         print("Sending utterance to coach:", running_transcript)

#                         response = conversation_engine(coach, running_transcript)
#                         response = json.loads(response)
#                         print("recieved response from coach")
#                         print(response)

#                         print("handle_llm_response")
#                         handle_llm_response(response) 
                        
#                 elif practicing:
#                     if len(running_transcript) >= batch_size:
#                         print("Sending to ridealong:", running_transcript)
#                         ridealong_response = conversation_engine(ridealong, running_transcript)
#                         ridealong_response = json.loads(ridealong_response)
#                         handle_llm_response(ridealong_response)
#                         if ridealong_response['action'] == "alert coach":
#                             full_transcript.append(running_transcript)
#                             running_transcript = ""

#             dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)

#         # print("ending listening")
#         # transcription_event.set()
#         # transcription_event.wait()
#         # transcription_event.clear()
        
#         # microphone.finish()
#         # # dg_connection.finish()
#         # print("Listening finished.")
#         # print("ready to listen again")

#     except Exception as e:
#         logging.error(f"Error: {e}")
#     finally:
#         if microphone:
#             microphone.finish()
#         stop_transcribing()

# @socketio.on('toggle_transcription')
# def toggle_transcription(data):
#     global transcribing
#     action = data.get('action')

#     if action == 'start' and not transcribing:
#         # Start transcription
#         transcribing = True
#         socketio.start_background_task(target=start_transcription_loop)
#     elif action == 'stop' and transcribing:
#         # Stop transcription
#         transcribing = False
#         transcription_event.set()

# control transcription state
# def start_transcribing():
#     global transcribing, transcription_event
#     if not transcribing:
#         transcribing = True
#         transcription_event.clear()  # Reset the event when starting
#         print("transcribing=true.")
#     else:
#         print("tried starting but already active.")

# def stop_transcribing():
#     global transcribing, transcription_event
#     if transcribing:
#         transcribing = False
#         transcription_event.set()  # Signal completion
#         print("transcribing=false")
#         # Additional cleanup code here
#     else:
#         print("tried stopping but already stopped")