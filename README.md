# nisa

scaling high quality instructional coaching

## progress as of 5.15

- Accesses notes that a coach has taken about the teacher

- Based on those notes AND memories that the AI has stored about user, AI creates a practice session:

    -  Topic of practice (AI gives its reasoning for choice to the backend but not to the user. Often the choice is based on an explicit humancoach request. If the coach hasn’t explicitly chosen a focus, the AI will infer one.)

    - Based on topic, generate look-fors and an internal thinking plan

- Engage in voice chat with tool calling (AI decides when to “listen” to user, when to officially start practice [ie send instructions to server], when to end session)


Next:

- Implement “real-ish time inference” that I developed in my authentic practice experiment

- Implement low fidelity memory update function

- Concurrently working on coach side: upload obs notes or (maybe) just send a text message with thoughts, and AI will confirm that they’ve understood coach correctly re: action steps/practice focus

- Playground mode would be great to work on. Trying to figure out what’s the most important thing.