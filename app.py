from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
    Microphone,
)
import time
from convo_tools import Nisa, create_json_bot
import json
from enum import Enum, auto
from openai import OpenAI
import random
from flask import Flask, render_template, Response, jsonify, request, redirect, url_for, send_from_directory
from flask_socketio import SocketIO, emit
import os
from threading import Event
import atexit
from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs

app = Flask(__name__)
socketio = SocketIO(app)

is_finals = []
final = ""
end_flag = False
coach = None
coach_response = ""
first_response = ""
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
speech_client = ElevenLabs(
    api_key=ELEVENLABS_API_KEY,
)
pending_action = None
user = None
last_audio = None
ridealong_exists = False
ridealong_reponse = None
practicing = False
dg_connection = None
microphone = None
transcription_event = Event()
batch = []
sending_to_ridealong = False
json_bot = create_json_bot("llama")
SESSION_TRANSCRIPT = []
intuition_prompts = {
    'respond': "your intuition is telling you to respond to the user. here is what the user said:",
    'keep listening': "your intuition is telling you to keep listening to the user. as a response to the user, you MUST say A VARIATION OF 'say more about that', etc. YOU MUST DO THIS. by doing so, you will be helping achieve your goal of creating a fluid conversation. stay on track: if you have already responded in this manner recently, you may ignore your intuition. here is what the user said:",
    'empathize': "your intuition is telling you to empathize with the user. empathize, but stay on track. here is what the user said:",
    'probe': "your intuition is telling you to probe the user. this means you should ask them to go deeper on what they just said, or you should ask them a question that surfaces some issue, conflict, problem, etc. here is what the user said:",
}

class State(Enum):
    IDLE = auto()
    WAITING_FOR_LLM_RESPONSE = auto()
    HANDLING_LLM_ACTION= auto()
    LISTENING = auto()
    GENERATING_SPEECH = auto()
    AWAITING_AUDIO_COMPLETION = auto()
    WAITING_FOR_USER_SIGNAL = auto()

current_state = State.IDLE

def cleanup():
    global dg_connection, microphone
    if dg_connection:
        dg_connection.finish()
        dg_connection = None
        print("cleaned up dg connection")
    if microphone:
        microphone.finish()
        microphone = None
        print("cleaned up microphone")
    print("cleaned up dg connection and microphone")
    
def handle_llm_action(action):
    global current_state
    global practicing
    if current_state == State.HANDLING_LLM_ACTION or practicing:
        action_map = {
            'listen to user': [listen, State.LISTENING],
            'end session': [exit, State.IDLE],
            'start practice': [start_practice, State.LISTENING], # will be a ridealong bot version of on_message(?)
            'redirect': [redirect_user, State.WAITING_FOR_LLM_RESPONSE], # only ridealong bot will be able to do this
            'reengage': [redirect_user, State.WAITING_FOR_LLM_RESPONSE], # only ridealong bot will be able to do this
        }
        action_function, next_state = action_map[action]
        current_state = next_state
        action_function()
    else:
        print(f"Invalid state for handling llm action: {current_state}")
        current_state = State.IDLE
        return
    
# future feature - if user needs a moment to think, keep mic open but only transcribe if user signal detected
# def take_a_moment():
#     global current_state
#     if current_state == State.WAITING_FOR_USER_SIGNAL:

#     else:
#         print(f"Invalid state for taking a moment: {current_state}")
#         current_state = State.IDLE
#     return

def start_practice():
    global coach
    global ridealong_exists
    global practicing

    if not practicing:
        practicing = True
        print("nisa called practice")
        if not ridealong_exists:
            coach.initiate_ridealong("llama")
            ridealong_exists = True
            socketio.emit('titleUpdate', {"title": f"Practicing {coach.scenario}"})
        socketio.start_background_task(target=live_transcribe)

def redirect_user():
    global ridealong_reponse
    global current_state
    global transcription_event
    global practicing
    global sending_to_ridealong
    global is_finals
    global SESSION_TRANSCRIPT
    if practicing:
        is_finals = []
        sending_to_ridealong = False
        if ridealong_reponse['action'] == 'redirect':
            socketio.emit('ui_sound',{'url':'/static/redirect.mp3'})
            emit_to_dom("nisa has <b>feedback!</b>", 'ui_flag','ui_flag')
            print("redirecting user")
        transcription_event.set()
        practicing = False
        SESSION_TRANSCRIPT.append("user: " + ridealong_reponse['context'])
        alert_message = f"message from practice assistant: {ridealong_reponse['message']}. teacher transcript so far: {ridealong_reponse['context']}. interrupt gently in order to redirect (eg: some variation of 'oh hold on let's pause for a second. [feedback]'. make sure to vary the way in which you do this, otherwise the user will feel like they are interacting with a canned response system, and you're not that!). you MUST use the 'start practice' action with your response to this prompt.)"
        current_state = State.WAITING_FOR_LLM_RESPONSE
        respond_to_user(alert_message)

def emit_to_dom(message, sender, message_type):
    global user
    if sender == 'user':
        message = f"<b>{user}</b>: {message}"
    elif sender == 'nisa':
        message = f"<b>nisa</b>: {message}"
    socketio.emit(message_type, {'sender': sender, 'message': message})
    print(f"emitting to dom: {message}")
    return

def text_to_speech(message):
    global last_audio, speech_client
    audio_directory = 'static/'

    filepath = f"{audio_directory}response{random.randint(1,1000)}.wav"

    # with speech_client.audio.speech.with_streaming_response.create(
    #     model="tts-1",
    #     voice="nova",
    #     input=message,
    #     response_format="wav",
    # ) as response:
    #     response.stream_to_file(filepath)

    response = speech_client.text_to_speech.convert(
        voice_id="P7x743VjyZEOihNNygQ9",  
        optimize_streaming_latency="0",
        output_format="mp3_22050_32",
        text=message,
        model_id="eleven_multilingual_v2",  # use the turbo model for low latency, for other languages use the `eleven_multilingual_v2`
        voice_settings=VoiceSettings(
            stability=0.5,
            similarity_boost=.75,
            style=0.0,
            use_speaker_boost=False,
        ),
    )
    # Writing the audio stream to the file
    with open(filepath, "wb") as f:
        for chunk in response:
            if chunk:
                f.write(chunk)
    
    last_audio = filepath
    return filepath

def speak_to_user(message):
    global current_state
    global speech_client
    
    if current_state == State.GENERATING_SPEECH:
        filepath = text_to_speech(message)
        current_state = State.AWAITING_AUDIO_COMPLETION
        print(f"attempting to play audio from {filepath}")
        socketio.emit('play_audio', {'url': f'{filepath}'})
    else:
        print(f"Invalid state for speaking to user: {current_state}")
        current_state = State.IDLE
        return

def respond_to_user(user_speech):
    global coach
    global coach_response
    global current_state
    global pending_action
    global practicing
    global SESSION_TRANSCRIPT
    global intuition_prompts

    if current_state == State.WAITING_FOR_LLM_RESPONSE:
        print(f"processing user speech: {user_speech}")
        intuition = coach.intuit(user_speech)
        if intuition in intuition_prompts.keys():
            print(f"intuition: {intuition}")
            user_speech = intuition_prompts[intuition] + user_speech
        emit_to_dom("nisa is <b>thinking...<b>", 'ui_flag','ui_flag')
        coach_response = coach.respond(user_speech)

        try:
            coach_response = json.loads(coach_response)
        except:
            print(f"error parsing JSON: {coach_response}")
            coach_response = json.loads(json_bot.invoke({"input":coach_response}))

        message = coach_response['message']
        action = coach_response['action']

        SESSION_TRANSCRIPT.append("nisa: " + message)

        emit_to_dom(message, 'nisa', 'chat_response')
        current_state = State.GENERATING_SPEECH
        speak_to_user(message)
        pending_action = action
    else:
        print(f"Invalid state for responding to user: {current_state}")
        current_state = State.IDLE
        return

def on_message(self, result, **kwargs):
    global is_finals
    global practicing
    global coach
    global current_state
    global json_bot
    global user

    chunk = result.channel.alternatives[0].transcript
    if len(chunk) > 1 & len(is_finals) == 0:
        print(f"sending user speech to client: {chunk}")
        socketio.emit('user_speech', {'speech': chunk, 'user': user})
    if result.is_final:
        is_finals.append(chunk)
        sentence = ' '.join(is_finals)
        socketio.emit('user_speech', {'speech': sentence, 'user': user})
    # print(f"speaker: {sentence}")

def on_utterance_end(self, utterance_end, **kwargs):
    global final
    global is_finals
    global current_state
    global end_flag
    global SESSION_TRANSCRIPT

    end_flag = True
    final = ' '.join(is_finals)
    SESSION_TRANSCRIPT.append("user: " + final)
    is_finals = []
    socketio.emit('ui_sound', {'url':'/static/stop.mp3'})
    # emit_to_dom(final, 'user', 'chat_response')
    current_state = State.WAITING_FOR_LLM_RESPONSE
    respond_to_user(final)

def on_open(self, open, **kwargs):
    print(f"\n\n{open}\n\n")

def on_error(self, error, **kwargs):
    print(f"\n\n{error}\n\n")

def on_close(self, close, **kwargs):
    print(f"\n\n{close}\n\n")

def on_speech_started(self, speech_started, **kwargs):
    print(f"\n\n{speech_started}\n\n")

def listen():
    global current_state, dg_connection, microphone, practicing
    global end_flag
    global user
    if current_state == State.LISTENING:
        if dg_connection or microphone:
            cleanup()
        socketio.emit('prepare_for_user_speech', {'user': user})
        socketio.emit('ui_sound', {'url':'/static/start.mp3'})
        emit_to_dom("nisa is <b>listening...</b>", 'ui_flag','ui_flag')
        end_flag = False
        deepgram: DeepgramClient = DeepgramClient()
        dg_connection = deepgram.listen.live.v("1")
        dg_connection.on(LiveTranscriptionEvents.Open, on_open)
        dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
        dg_connection.on(LiveTranscriptionEvents.SpeechStarted, on_speech_started)
        dg_connection.on(LiveTranscriptionEvents.UtteranceEnd, on_utterance_end)
        dg_connection.on(LiveTranscriptionEvents.Error, on_error)
        dg_connection.on(LiveTranscriptionEvents.Close, on_close)

        options: LiveOptions = LiveOptions(
            model="nova-2",
            punctuate=True,
            language="en-US",
            encoding="linear16",
            filler_words=True,
            channels=1,
            sample_rate=16000,
            # To get UtteranceEnd, the following must be set:
            interim_results=True,
            utterance_end_ms="1500",
            vad_events=True,
        )

        dg_connection.start(options)

        # create microphone
        microphone = Microphone(dg_connection.send)

        # start microphone
        microphone.start()

        # wait until finished
        while True:
            if end_flag:
                cleanup()
                break
    else:
        print(f"Invalid state for conversation: {current_state}")
        current_state = State.IDLE
        return
    
def on_message_live(self, result, **kwargs):
    global is_finals
    global practicing
    global coach
    global current_state
    global json_bot
    global batch
    global sending_to_ridealong

    batch_size = 3

    chunk = result.channel.alternatives[0].transcript
    if len(chunk) > 1 & len(is_finals) == 0:
        print(f"sending user speech to client: {chunk}")
        socketio.emit('user_speech', {'speech': chunk, 'user': user})
    print(f"speaker: {chunk}")
    if result.is_final:
        is_finals.append(chunk)
        sentence = ' '.join(is_finals)
        socketio.emit('user_speech', {'speech': sentence, 'user': user})
        batch.append(chunk)

    if len(batch) >= batch_size:
        if not sending_to_ridealong:
            sending_to_ridealong = True
            snippet = ' '.join(batch)
            running_transcript = ' '.join(is_finals)
            ridealong_message = f"teacher just said: {snippet}. teacher transcript so far: {running_transcript}"
            print(f"sending snippet to ridealong: {snippet}")
            batch = []
            send_to_ridealong(ridealong_message)

def send_to_ridealong(ridealong_message):
    global sending_to_ridealong
    global pending_action
    global ridealong_reponse
    if sending_to_ridealong:
        response = coach.live_inference(ridealong_message)
        try:
            ridealong_reponse = json.loads(response)
        except:
            print(f"error parsing JSON: {response}")
            ridealong_reponse = json.loads(json_bot.invoke({"input":response}))
        print(f"response from ridealong: {ridealong_reponse}")
        action = ridealong_reponse['action']
        if action:
            print(f"action from ridealong: {action}")
            if action == 'continue':
                sending_to_ridealong = False
            else:
                handle_llm_action(action)
    
def live_transcribe():
    global current_state, practicing, transcription_event
    
    if current_state == State.LISTENING:
        if practicing:   # function should only be called if these are true, but just making sure.
            print("starting live transcription")
            socketio.emit('prepare_for_user_speech', {'user': user})
            socketio.emit('ui_sound', {'url':'/static/start.mp3'})
            emit_to_dom("nisa is <b>taking notes...</b>", 'ui_flag','ui_flag')
            while practicing:
                config = DeepgramClientOptions(
                            options={"keepalive": "true"}
                        )
                live_deepgram: DeepgramClient = DeepgramClient("",config)
                live_dg_connection = live_deepgram.listen.live.v("1")
                live_dg_connection.on(LiveTranscriptionEvents.Open, on_open)
                live_dg_connection.on(LiveTranscriptionEvents.Transcript, on_message_live)
                live_dg_connection.on(LiveTranscriptionEvents.SpeechStarted, on_speech_started)
                live_dg_connection.on(LiveTranscriptionEvents.Error, on_error)
                live_dg_connection.on(LiveTranscriptionEvents.Close, on_close)

                options: LiveOptions = LiveOptions(
                                        smart_format=True,
                                        model="nova-2",
                                        filler_words=True,
                                        language="en-US",
                                        encoding="linear16",
                                        channels=1,
                                        sample_rate=16000,
                                        )

                live_dg_connection.start(options)

                # create microphone
                live_microphone = Microphone(live_dg_connection.send)

                # start microphone
                live_microphone.start()

                transcription_event.wait()
                transcription_event.clear()

                live_microphone.finish()
                live_dg_connection.finish()

def save_session_transcript():
    global SESSION_TRANSCRIPT
    global user
    timestamp = time.time()
    filename = f"{user}_transcript_{timestamp}.txt"
    with open(filename, 'w') as file:
        file.write('\n'.join(SESSION_TRANSCRIPT))

def save_memories():
    global coach, user, SESSION_TRANSCRIPT
    updated_memory = coach.remember('\n'.join(SESSION_TRANSCRIPT))
    timestamp = time.time()
    filename = f"updated_memories_{timestamp}.txt"
    with open(filename, 'w') as file:
        file.write(updated_memory)

@app.route('/')
def login():
    return render_template('login.html')

@app.route('/generate_session', methods=['POST'])
def generate_session():
    global coach
    global first_response
    global SESSION_TRANSCRIPT
    user_name = request.form['user_name']

    # socketio.emit('ui_sound', {'url':'/static/startintro.mp3'})

    coach = Nisa("llama", user_name) # 'gpt'= gpt 4o; 'llama' = llama 3 70b via Groq; 'haiku' = claude haiku
    coach.initialize_intuition()
    SESSION_TRANSCRIPT.append(f"SESSION TRANSCRIPT FOR {user_name}")
    SESSION_TRANSCRIPT.append(f"{coach.scenario}")
    SESSION_TRANSCRIPT.append(f"{coach.look_fors}")
    SESSION_TRANSCRIPT.append(f"{coach.thinking_plan}")
    SESSION_TRANSCRIPT.append(f"\nBEGIN TRANSCRIPT\n")
    title = coach.practice_context['scenario'].split('Reasoning')[0].strip().lower()
    socketio.emit('ui_sound', {'url':'/static/loaded.mp3'})
    first_response = coach.respond("begin session. do not acknowledge receipt of this message.")
    # first_response = coach.respond("hey this is the developer (my name really is agasthya but im not currently a teacher haha). just testing the system, so i might ask you to do specific functions. thanks for helping improve the system! it's very important that you still follow all formatting rules.")
    try:
        first_response = json.loads(first_response)
    except:
        print(f"error parsing JSON: {first_response}")
        first_response = json_bot.invoke({"input":first_response})
        print(f"response from json bot: {first_response}")
        first_response = json.loads(first_response)
    return redirect(url_for('index', user=user_name, title=title))

@app.route('/index')
def index():
    global user
    user_name = request.args.get('user', 'Guest')
    title = request.args.get('title', 'Practice')
    user = user_name
    greeting = f"Hi, {user_name}. Today we'll be focusing on {title} Let's get started!"
    print(greeting)
    return render_template('index.html', user_name=user_name, greeting=greeting)

@socketio.on('request_initial_message')
def handle_initial_message():
    global current_state
    global first_response
    global pending_action
    global SESSION_TRANSCRIPT

    print(f"Received 'request_initial_message' event from client with SID: {request.sid}")
    message = first_response['message']
    action = first_response['action']

    SESSION_TRANSCRIPT.append("nisa: " + message)

    emit_to_dom(message, 'nisa', 'chat_response')
    current_state = State.GENERATING_SPEECH
    speak_to_user(message)
    pending_action = action
    # current_state = State.HANDLING_LLM_ACTION
    # handle_llm_action(action)

@app.route('/static/<filename>')
def serve_audio(filename):
    return send_from_directory('static', filename)

@socketio.on('audio_finished')
def on_audio_finished():
    print("Received 'audio_finished' event from client.")
    global current_state
    global pending_action
    global last_audio
    if current_state == State.AWAITING_AUDIO_COMPLETION:
        os.remove(last_audio)
        print(f"deleted audio file {last_audio}")
        current_state = State.HANDLING_LLM_ACTION
        handle_llm_action(pending_action)
    else:
        print("Audio finished at an unexpected time.")

@atexit.register
def shutdown_hook():
    global user 
    if user:
        save_session_transcript()
        save_memories()

if __name__ == '__main__':
    print("Starting SocketIO server.")
    socketio.run(app, debug=True)