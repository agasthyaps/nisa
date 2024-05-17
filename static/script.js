document.addEventListener('DOMContentLoaded', function() {
  var socket = io();

  socket.on('connect', function() {
    console.log('Connected to the server');
    console.log('Client session ID:', socket.id);
  });


  socket.on('chat_response', function(data) {
    console.log("Received 'chat_response' event:");
    console.log(data);
    addMessage(data, 'chat-messages');
  });

  socket.on('ui_flag', function(data) {
    console.log("Received 'ui_flag' event:");
    // console.log(data);
    addMessage(data, 'uiFeedback');
  });

  socket.on('ui_sound', function(data) {
    const audioPlayer = document.getElementById('audioUIPlayer');
    audioPlayer.src = data.url;
    audioPlayer.play();
  });

  socket.on('play_audio', function(data) {
    console.log("Received 'play_audio' event:");

    const ui_container = document.getElementById('feedback-area');
    const messages = ui_container.querySelectorAll('p');
    if (messages.length > 0){
      messages[0].remove(); // Remove the last UI message
    }
    // Get the audio player and audio visualizer elements
    const audioPlayer = document.getElementById('audioPlayer');
    const audioVisualizer = document.getElementById('audioVisualizerImg');

    // Set the new audio source and make the audio player visible
    audioPlayer.src = data.url;

    // Play the audio
    audioPlayer.play();

    audioVisualizer.hidden = false;  // Show the visualizer by removing the hidden attribute

    // Handle when the audio finishes playing
    audioPlayer.onended = function() {
        // Add the hidden attribute back to hide the visualizer when audio ends
        audioVisualizer.hidden = true;

        // Emit the audio finished event to the server
        socket.emit('audio_finished');

        // Optionally, remove messages if necessary
    };
  });

  function prepare_for_user_speech(data){
    const user = data.user
    const chatContainer = document.getElementById('chat-messages');
    const userMessageContainer = document.createElement('p');
    userMessageContainer.className = 'user';
    // userMessageContainer.innerHTML = "<b>" + user + "</b>: ";
    userMessageContainer.style.color = '#605353'; // Dark gray for user
    userMessageContainer.style.fontStyle = 'regular';

    chatContainer.appendChild(userMessageContainer);
    chatContainer.scrollTop = chatContainer.scrollHeight;
  }

  socket.on('prepare_for_user_speech', function(data){
    prepare_for_user_speech(data);
  });

  function display_live_transcription(data){
    const chatContainer = document.getElementById('chat-messages');
    const userParagraphs = chatContainer.querySelectorAll('p.user');
    const mostRecentUserParagraph = userParagraphs[userParagraphs.length - 1];
    const user = data.user;

    // Check if the element exists before trying to use it
    if (mostRecentUserParagraph) {
      mostRecentUserParagraph.innerHTML = "<b>" + user + "</b>: " + data.speech;
    }
    chatContainer.scrollTop = chatContainer.scrollHeight;
    updateOpacityBasedOnScroll(chatContainer);
  }

  socket.on('user_speech', function(data){
    console.log("Received 'user_speech' event:");
    console.log(data);
    display_live_transcription(data);
  });

  function addMessage(data, elemid) {
    const container = document.getElementById(elemid);
    const newMessage = document.createElement('p');
    newMessage.innerHTML = data.message;

    // Apply different styles based on the sender
    if (data.sender === 'nisa') {
      newMessage.style.color = 'white'; // White for nisa
      newMessage.style.fontStyle = 'regular';
    } 
    // if (data.sender === 'user') {
    //   newMessage.style.color = '#605353'; // Dark gray for user
    //   newMessage.style.fontStyle = 'regular';
    // }
    if (data.sender === 'ui_flag') {
      newMessage.style.color = 'white'; // everything else
      newMessage.style.fontStyle = 'italic'; 
      newMessage.style.animation = 'fadeOpacity 2s infinite';
    }

    container.appendChild(newMessage);
    container.scrollTop = container.scrollHeight; // Ensure the container scrolls to the new message
    
    // Update the appearance of messages
    const messages = container.querySelectorAll('p');
    
    if (data.sender === 'ui_flag'){
      // We don't want to stack the UI messages
      if(messages.length > 1){
        messages[0].remove();
      }
    }

    // Apply opacity gradation to messages
    updateOpacityBasedOnScroll(container);
  }

  function updateOpacityBasedOnScroll(container) {
    const isAtBottom = container.scrollHeight - container.scrollTop === container.clientHeight;
    const messages = container.querySelectorAll('p');
    if (isAtBottom) {
        // Apply fading opacity to the last few messages only when at the bottom
        messages.forEach((msg, index) => {
            if (index < messages.length - 5) {
                msg.style.opacity = 0;  // Older messages are not visible
            } else {
                msg.style.opacity = 1 - 0.20 * (messages.length - index - 1);
            }
        });
    } else {
        // Make all messages fully visible when not at the bottom
        messages.forEach(msg => msg.style.opacity = 1);
    }
  }

  document.getElementById('navPractice').addEventListener('click', function() {
    setActiveNavItem('navPractice');
  });

  document.getElementById('navPlayground').addEventListener('click', function() {
    setActiveNavItem('navPlayground');
  });

  function setActiveNavItem(activeId) {
    // Remove active class from all nav items
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });

    // Add active class to the clicked nav item
    document.getElementById(activeId).classList.add('active');
  }

  // Socket event to handle button text updates and show the button
  socket.on('btnmaker', function(data) {
    console.log("Received 'btnmaker' with data:", data);
    const button = document.getElementById('dynamicBtn');
    button.textContent = data.text; // Update button text
    button.hidden = false; // Show the button
  });

  document.getElementById('dynamicBtn').addEventListener('click', function() {
    var button = document.getElementById('dynamicBtn');  // Ensure 'var' or 'let' is used for local scoping
    if (button.textContent === "start session") {
        console.log("start session");
        document.getElementById('sessionContext').hidden = true;
        document.getElementById('sessionContext').style.display = 'none';
        socket.emit('request_initial_message');
    } else {
        console.log("wrong text");
    }
    button.hidden = true;  // This should hide the button after clicking
    // Force a reflow if necessary
    button.style.display = 'none';
  });

  socket.on('titleUpdate', function(data) {
    console.log("Received titleUpdate");
    console.log(data);
    const sessionContext = document.getElementById('sessionContext');
    sessionContext.textContent = data.text; // Update the text from the server

    // Ensure element is initially set to invisible for the fade effect to trigger
    sessionContext.classList.remove('visible');
    sessionContext.hidden = false; // Ensure the element is not hidden by HTML attribute

    // Use setTimeout to allow the browser to render the element as hidden first
    setTimeout(function() {
        sessionContext.classList.add('visible');
    }, 10); // Small delay to ensure the class change triggers the transition effect
});



  // Add event listener to handle scroll events
  document.getElementById('chat-messages').addEventListener('scroll', function() {
    updateOpacityBasedOnScroll(this);
  });

  document.getElementById('audioVisualizerImg').hidden = true; // Hide the audio visualizer initially
  // console.log('Emitting "request_initial_message" event');
});




  

