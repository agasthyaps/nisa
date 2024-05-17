# nisa

scaling high quality instructional coaching with genAI


## progress as of 5.17


https://github.com/agasthyaps/nisa/assets/31672319/9efa4df5-dc3a-4a1c-a3c4-c509197a053a

- live practice loop now integrated - nisa interrupts user as soon as it notices the need for a redirect (**jump to 2:35 in the video above to see it in action**)
- some UI stuff to reduce percieved latency:
    - mic open/off audio feedback makes lets you know that nisa thinks you're done talking and is about to respond (rather than the awkward dead air in the video below)
    - live transcription of your voice on screen gives you something to look at
    - 'ding' on redirect interrupts user before speech is synthesized so user doesn't keep talking for too long
- Next:
    - nisa decides when session is done
    - separate memory module, use session transcript to extract relevant memories, store in database
    - still sketching out coach view (likely: text a pic of obs notes + some thoughts, AI texts you back to tell you what it thinks it should focus on with teacher, you correct it or tell it good job -> goes into database for next teacher interaction)
    - playground on backburner for now

## progress as of 5.15



https://github.com/agasthyaps/nisa/assets/31672319/72aa5ddb-51f1-4e0d-b6b7-c93cb4878a62



- Accesses notes that a coach has taken about the teacher
- Based on those notes AND memories that the AI has stored about user, AI creates a practice session:
    -  Topic of practice (AI gives its reasoning for choice to the backend but not to the user. Often the choice is based on an explicit humancoach request. If the coach hasn’t explicitly chosen a focus, the AI will infer one.)
    - Based on topic, generate look-fors and an internal thinking plan
- Engage in voice chat with tool calling (AI decides when to “listen” to user, when to officially start practice [ie send instructions to server], when to end session)
- Currently using **llama 3 via Groq** for inference, **deepgram** for transcription, **openai** for text-to-speech.


Next:

- Implement “real-ish time inference” that I developed in my authentic practice experiment
- Implement low fidelity memory update function
- Concurrently working on coach side: upload obs notes or (maybe) just send a text message with thoughts, and AI will confirm that they’ve understood coach correctly re: action steps/practice focus
- Playground mode would be great to work on. Trying to figure out what’s the most important thing.

## usage

Haven't checked if this runs on another machine but as long as you have API keys for Groq, Deepgram, and OpenAI (`export PROVIDER_API_KEY='api-key'`) and install requirements.txt you should be able to run it (`python app.py`)
