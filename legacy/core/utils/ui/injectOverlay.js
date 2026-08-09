let awaitingUserResponse = false;
let show_details = true;

function injectOveralyStyles() {
  let style = document.createElement("style");
  style.textContent = `
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&family=Lato:wght@300;400;700&display=swap');

    ::-webkit-scrollbar {
      width: 6px;
      border: solid 3px transparent;
    }

    ::-webkit-scrollbar-track {
      background-color: transparent;
    }

    ::-webkit-scrollbar-thumb {
      background-color: #757575;
      border-radius: 6px;
    }

    ::-webkit-scrollbar-thumb:hover {
      background-color: white;
    }

    .tawebagent-ui-automation-highlight {
      border-width: 2px !important;
      border-style: solid !important;
      animation: automation_highlight_fadeout_animation 5s linear 1 forwards !important;
    }

    @keyframes automation_highlight_fadeout_animation {
      0% { border-color: rgba(147, 51, 234, 1); }
      50% { border-color: rgba(147, 51, 234, 1); }
      100% { border-color: rgba(147, 51, 234, 0); }
    }

    .tawebagent-processing {
      background: linear-gradient(135deg, #4F46E5, #9333EA);
      animation: tawebagent-gradient-shift 3s ease infinite;
    }

    @keyframes tawebagent-gradient-shift {
      0% { background-position: 0% 50%; }
      50% { background-position: 100% 50%; }
      100% { background-position: 0% 50%; }
    }

    .tawebagent-init {
      background: #F3F4F6;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    }

    .tawebagent-done {
      background: linear-gradient(135deg, #059669, #10B981);
    }

    .tawebagent-collapsed {
      cursor: pointer;
      width: 54px;
      height: 54px;
      border-radius: 12px;
      position: fixed;
      right: 24px;
      bottom: 24px;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.3s ease;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
      background: hsla(132, 52%, 47%, 1);
      z-index: 2147483646;
    }

    .tawebagent-collapsed:hover {
      transform: scale(1.05);
      box-shadow: 0 6px 16px rgba(0, 0, 0, 0.2);
    }

    .tawebagent-chat-container {
margin: 0;
    width: 380px;
    height: 600px;
    position: fixed;
    display: flex;
    flex-direction: column;
    right: 24px;
    bottom: 24px;
    background: hsla(0, 0%, 7%, 1);
    border-radius: 8px;
    box-shadow: 4px 4px 8px 0px rgba(0, 0, 0, 0.25);
    overflow: hidden;
    z-index: 2147483646;
    border: 1px solid var(--O5---500, rgba(51, 51, 51, 1));
}

  #tawebagent-chat-box {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: calc(100% - 240px); /* Explicit height calculation */
  min-height: 200px; /* Minimum height */
  margin: 0;
}



  .tawebagent-chat-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px;
    background: hsla(0, 0%, 7%, 1);
    height: 36px;
    min-height: 36px;
}

    .tawebagent-logo-container {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .tawebagent-logo {
      width: 32px;
      height: 32px;
      background: linear-gradient(135deg, #4F46E5, #9333EA);
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .tawebagent-logo-inner {
      width: 24px;
      height: 24px;
      background: white;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .tawebagent-logo-core {
      width: 16px;
      height: 16px;
      background: linear-gradient(135deg, #4F46E5, #9333EA);
      border-radius: 50%;
    }

    .tawebagent-title {
      font-family: DM Sans, serif;
      font-weight: 600;
      font-size: 16px;
      color: #1F2937;
    }

   .tawebagent-chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0; /* This is crucial for proper scrolling */
  max-height: calc(100% - 180px); /* Adjust based on header + input + settings height */
}

   .tawebagent-message {
    max-width: 85%;
    padding: 12px 16px;
    border-radius: 10px;
    font-family: 'DM Sans', serif;
    font-size: 14px;
    line-height: 1.5;
    overflow: hidden; /* Ensure content does not overflow the container */
    white-space: pre-wrap; /* Allow wrapping and preserve line breaks */
    word-wrap: break-word; /* Handle long words gracefully */
}

.tawebagent-user-message {
    align-self: flex-end;
    background: rgba(57, 181, 82, 1);
    color: white;
}

.tawebagent-system-message {
    align-self: flex-start;
    background: none;
    color: white;
    border: 1px solid var(--O5---500, rgba(51, 51, 51, 1));
}

/* Specific styling for preformatted text within messages */
.tawebagent-message pre {
    margin: 0; /* Remove default margin of <pre> */
    white-space: pre-wrap; /* Preserve whitespace and line breaks, allow wrapping */
    word-wrap: break-word; /* Break long words */
    overflow: auto; /* Add scrollbars if necessary */
}

   .tawebagent-input-container {
    margin: 0 16px;
    padding: 0px 10px;
    background: var(--O2---200, rgba(24, 24, 24, 1));
    margin-bottom: 38px;
    z-index: 2;
    border: 1px solid var(--O5---500, rgba(51, 51, 51, 1));
    border-radius: 6px;

}

    .tawebagent-input-wrapper {
    position: relative;
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 8px;
    padding-top: 14px;
    border-top: 1px solid var(--O5---500, rgba(51, 51, 51, 1));
}

  .tawebagent-textarea {
    width: 100%;
    max-height: 75px;
    min-height: 28px;
    padding: 4px 0px;
    border: none;
    font-family: DM Sans, serif;
    font-size: 15px;
    resize: none;
    transition: all 0.2s ease;
    background: transparent;
    margin-bottom: 0;
    color: white;
}

    .tawebagent-textarea:focus {
      outline: none;
      
    }

    .tawebagent-send-button {
  display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.2s ease;
    flex-shrink: 0;
    margin-top: 2px;
        background: transparent;
    border: none;
}

    .tawebagent-send-button-enabled {
      // background: linear-gradient(135deg, #4F46E5, #9333EA);
      color: white;
    }

    .tawebagent-send-button-disabled {
      color: #757575;
    }

    button:disabled {
     opacity: 1;
     background: none;
     border: none;
     outline: none;
     pointer-events: none;
     cursor: default;
    }

    button:disabled svg {
     opacity: 0.5;
    }

    .tawebagent-settings-bar {
    display: flex;
    align-items: center;
    padding: 14px 8px;
    justify-content: space-between;
}

.tawebagent-overlay-wrapper {
  position: fixed;
  right: 24px;
  bottom: 24px;
  pointer-events: none;
  z-index: 2147483646;
}

.tawebagent-overlay-wrapper > * {
  pointer-events: auto;
}

    .tawebagent-toggle-container {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .tawebagent-toggle {
       position: relative;
      width: 28px;
      height: 16px;
      background: #E5E7EB;
      border-radius: 10px;  /* Slightly reduced to match design */
      cursor: pointer;
      transition: all 0.2s ease;
      display: inline-block;
    }

    .tawebagent-toggle-checked {
      background: white;
    }

    .tawebagent-toggle-thumb {
      position: absolute;
      top: 2px;          /* Adjusted from 0.5px for better centering */
      left: 2px;         /* Adjusted from 2px */
      width: 13px;       /* Slightly reduced for better fit */
      height: 13px;      /* Slightly reduced for better fit */
      border-radius: 50%;
      transition: all 0.2s ease;
      background: #757575;
    }
      
      .tawebagent-toggle-checked .tawebagent-toggle-thumb {
        background: hsla(0, 0%, 9%, 1);
        left: 13px;
    }

   .tawebagent-disclaimer {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    font-family: DM Sans, serif;
    font-size: 11px;
    color: white;
    display: flex;
    align-items: center;
    gap: 8px;
    z-index: 3;
    height: 40px;
    justify-content: center;
}
  `;
  document.head.appendChild(style);
}

function showCollapsedOverlay(processing_state = "processing") {
  removeOverlay();
  window.overlay_state_changed(true);

  // Create wrapper
  const wrapper = document.createElement("div");
  wrapper.id = "tawebagent-overlay-wrapper";
  wrapper.className = "tawebagent-overlay-wrapper";

  // // Create main container
  const collapsed = document.createElement("div");
  collapsed.id = "tawebagent-overlay";
  collapsed.classList.add("tawebagent-collapsed");

  const sendIcon = createSvgIcon("collapsed");

  // // Create gradient background wrapper
  // const gradientWrapper = document.createElement("div");

  collapsed.appendChild(sendIcon);

  // Add state-based styling
  updateOverlayState(processing_state, true);

  // Add event listeners
  collapsed.addEventListener("mouseover", () => {
    collapsed.style.transform = "scale(1.05)";
  });

  collapsed.addEventListener("mouseout", () => {
    collapsed.style.transform = "scale(1)";
  });

  collapsed.addEventListener("click", () => {
    const state = document
      .getElementById("tawebagent-overlay")
      .querySelector(".tawebagent-processing")
      ? "processing"
      : document
          .getElementById("tawebagent-overlay")
          .querySelector(".tawebagent-done")
      ? "done"
      : "init";
    showExpandedOverlay(state, show_details);
  });

  wrapper.appendChild(collapsed);
  document.body.appendChild(wrapper);
}

function updateOverlayState(processing_state, is_collapsed) {
  const element = is_collapsed
    ? document.getElementById("tawebagent-overlay")
    : document.getElementById("tawebagentExpandedAnimation");

  if (!element) return;

  // Remove all state classes
  element.classList.remove(
    "tawebagent-init",
    "tawebagent-processing",
    "tawebagent-done",
    "tawebagent-initStateLine",
    "tawebagent-processingLine",
    "tawebagent-doneStateLine"
  );

  if (is_collapsed) {
    switch (processing_state) {
      case "init":
        element.classList.add("tawebagent-init");
        enableOverlay();
        break;
      case "processing":
        element.classList.add("tawebagent-processing");
        disableOverlay();
        break;
      case "done":
        element.classList.add("tawebagent-done");
        enableOverlay();
        break;
    }
  } else {
    switch (processing_state) {
      case "init":
        element.classList.add("tawebagent-initStateLine");
        enableOverlay();
        break;
      case "processing":
        element.classList.add("tawebagent-processingLine");
        disableOverlay();
        break;
      case "done":
        element.classList.add("tawebagent-doneStateLine");
        enableOverlay();
        break;
    }
  }
}

function createSvgIcon(type) {
  const icons = {
    send: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 2L11 13M22 2L15 22L11 13M11 13L2 9L22 2"/>
          </svg>`,
    close: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
             <path d="M18 6L6 18M6 6l12 12"/>
           </svg>`,
    minimize: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/>
              </svg>`,
    alert: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
             <circle cx="12" cy="12" r="10"/>
             <line x1="12" y1="8" x2="12" y2="12"/>
             <line x1="12" y1="16" x2="12.01" y2="16"/>
           </svg>`,
    //  new
    logo: `<svg width="108" height="24" viewBox="0 0 108 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M4.80475 19.3975C4.01481 19.3975 3.31812 19.211 2.71469 18.8379C2.11126 18.4539 1.63949 17.9383 1.29938 17.291C0.970236 16.6327 0.805664 15.8866 0.805664 15.0528C0.805664 14.208 0.975721 13.4619 1.31584 12.8146C1.65595 12.1673 2.12772 11.6571 2.73115 11.2841C3.33458 10.9001 4.03126 10.7081 4.82121 10.7081C5.46852 10.7081 6.03904 10.8398 6.53275 11.1031C7.02646 11.3664 7.41046 11.7284 7.68475 12.1892L7.79995 10.9056H9.33046V19.2H7.81641L7.68475 17.9163C7.43241 18.3003 7.07035 18.6459 6.59858 18.9531C6.12681 19.2494 5.52886 19.3975 4.80475 19.3975ZM5.06806 17.9657C5.58372 17.9657 6.03904 17.845 6.43401 17.6036C6.82898 17.3623 7.13069 17.0222 7.33915 16.5833C7.55858 16.1444 7.66829 15.6343 7.66829 15.0528C7.66829 14.4713 7.55858 13.9666 7.33915 13.5387C7.13069 13.0999 6.82898 12.7598 6.43401 12.5184C6.03904 12.266 5.58372 12.1399 5.06806 12.1399C4.57435 12.1399 4.13001 12.266 3.73504 12.5184C3.34006 12.7598 3.03286 13.0999 2.81344 13.5387C2.59401 13.9666 2.48429 14.4713 2.48429 15.0528C2.48429 15.6343 2.59401 16.1444 2.81344 16.5833C3.03286 17.0222 3.34006 17.3623 3.73504 17.6036C4.13001 17.845 4.57435 17.9657 5.06806 17.9657ZM14.4608 23.018C13.9232 23.018 13.4186 22.9522 12.9468 22.8206C12.475 22.6889 12.0471 22.4859 11.6631 22.2116C11.2791 21.9483 10.961 21.6192 10.7086 21.2242C10.4563 20.8402 10.2862 20.3904 10.1984 19.8747H11.8442C11.9429 20.2148 12.1075 20.5111 12.3379 20.7634C12.5792 21.0267 12.8755 21.2297 13.2266 21.3723C13.5886 21.515 13.9891 21.5863 14.4279 21.5863C14.9216 21.5863 15.366 21.482 15.761 21.2736C16.1559 21.0761 16.4686 20.7634 16.699 20.3355C16.9294 19.9186 17.0446 19.392 17.0446 18.7556V17.6366C16.8691 17.9218 16.6442 18.1906 16.3699 18.443C16.0956 18.6953 15.761 18.8983 15.366 19.0519C14.982 19.2055 14.5376 19.2823 14.033 19.2823C13.254 19.2823 12.5573 19.0958 11.9429 18.7227C11.3395 18.3497 10.8567 17.8395 10.4947 17.1922C10.1326 16.5449 9.95158 15.8098 9.95158 14.987C9.95158 14.1531 10.1326 13.418 10.4947 12.7817C10.8567 12.1344 11.345 11.6297 11.9594 11.2676C12.5847 10.8946 13.2759 10.7081 14.033 10.7081C14.4938 10.7081 14.9162 10.7794 15.3002 10.922C15.6842 11.0537 16.0243 11.2402 16.3205 11.4816C16.6167 11.712 16.8581 11.9698 17.0446 12.2551L17.1927 10.9056H18.6903V18.7063C18.6903 19.4084 18.5806 20.0228 18.3612 20.5495C18.1527 21.0871 17.8565 21.5369 17.4725 21.899C17.0995 22.261 16.6551 22.5353 16.1395 22.7218C15.6238 22.9193 15.0643 23.018 14.4608 23.018ZM14.3127 17.8505C14.8394 17.8505 15.3056 17.7298 15.7116 17.4884C16.1175 17.2361 16.4302 16.896 16.6496 16.4681C16.88 16.0402 16.9952 15.5465 16.9952 14.987C16.9952 14.4164 16.88 13.9227 16.6496 13.5058C16.4302 13.0779 16.1175 12.7433 15.7116 12.5019C15.3056 12.2606 14.8394 12.1399 14.3127 12.1399C13.7971 12.1399 13.3363 12.2606 12.9303 12.5019C12.5244 12.7433 12.2062 13.0779 11.9758 13.5058C11.7454 13.9227 11.6302 14.4164 11.6302 14.987C11.6302 15.5465 11.7454 16.0402 11.9758 16.4681C12.2062 16.896 12.5244 17.2361 12.9303 17.4884C13.3363 17.7298 13.7971 17.8505 14.3127 17.8505ZM23.3714 19.3975C22.5814 19.3975 21.8792 19.2164 21.2648 18.8544C20.6504 18.4923 20.1677 17.9876 19.8166 17.3403C19.4765 16.693 19.3064 15.9415 19.3064 15.0857C19.3064 14.208 19.4765 13.4455 19.8166 12.7982C20.1677 12.1399 20.6504 11.6297 21.2648 11.2676C21.8792 10.8946 22.5924 10.7081 23.4043 10.7081C24.2162 10.7081 24.9128 10.8891 25.4943 11.2512C26.0758 11.6132 26.5256 12.096 26.8438 12.6994C27.162 13.2919 27.3211 13.9502 27.3211 14.6743C27.3211 14.784 27.3156 14.9047 27.3046 15.0363C27.3046 15.157 27.2991 15.2942 27.2882 15.4478H20.5078V14.2793H25.6754C25.6424 13.5881 25.412 13.0505 24.9842 12.6665C24.5563 12.2715 24.0242 12.074 23.3878 12.074C22.938 12.074 22.5266 12.1783 22.1535 12.3867C21.7805 12.5842 21.4788 12.8804 21.2484 13.2754C21.029 13.6594 20.9192 14.1476 20.9192 14.7401V15.2009C20.9192 15.8153 21.029 16.3364 21.2484 16.7643C21.4788 17.1812 21.7805 17.4994 22.1535 17.7188C22.5266 17.9273 22.9325 18.0315 23.3714 18.0315C23.898 18.0315 24.3314 17.9163 24.6715 17.6859C25.0116 17.4555 25.2639 17.1428 25.4285 16.7479H27.0742C26.9316 17.2526 26.6902 17.7079 26.3501 18.1138C26.01 18.5088 25.5876 18.8215 25.0829 19.0519C24.5892 19.2823 24.0187 19.3975 23.3714 19.3975ZM27.833 19.2V10.9056H29.3141L29.4128 12.3209C29.6762 11.8272 30.0492 11.4377 30.5319 11.1524C31.0147 10.8562 31.5687 10.7081 32.1941 10.7081C32.8524 10.7081 33.4174 10.8398 33.8892 11.1031C34.361 11.3664 34.7285 11.7668 34.9918 12.3044C35.2551 12.8311 35.3868 13.4948 35.3868 14.2958V19.2H33.7411V14.4603C33.7411 13.6923 33.571 13.1108 33.2309 12.7159C32.8908 12.3209 32.3971 12.1234 31.7498 12.1234C31.3219 12.1234 30.9379 12.2276 30.5978 12.4361C30.2576 12.6336 29.9834 12.9298 29.7749 13.3248C29.5774 13.7198 29.4787 14.2025 29.4787 14.773V19.2H27.833ZM39.5984 19.2C39.0717 19.2 38.6164 19.1177 38.2324 18.9531C37.8484 18.7886 37.5522 18.5143 37.3437 18.1303C37.1353 17.7463 37.0311 17.2251 37.0311 16.5668V12.3044H35.5993V10.9056H37.0311L37.2285 8.83198H38.6768V10.9056H41.0301V12.3044H38.6768V16.5833C38.6768 17.0551 38.7755 17.3787 38.973 17.5543C39.1705 17.7188 39.5106 17.8011 39.9933 17.8011H40.9479V19.2H39.5984ZM41.6436 19.2V10.9056H43.2893V19.2H41.6436ZM42.4829 9.34215C42.1647 9.34215 41.9014 9.24341 41.693 9.04593C41.4955 8.84844 41.3967 8.5961 41.3967 8.2889C41.3967 7.99267 41.4955 7.7513 41.693 7.56478C41.9014 7.3673 42.1647 7.26855 42.4829 7.26855C42.7901 7.26855 43.0479 7.3673 43.2564 7.56478C43.4648 7.7513 43.5691 7.99267 43.5691 8.2889C43.5691 8.5961 43.4648 8.84844 43.2564 9.04593C43.0479 9.24341 42.7901 9.34215 42.4829 9.34215ZM48.1606 19.3975C47.3597 19.3975 46.6465 19.2164 46.0211 18.8544C45.3957 18.4814 44.902 17.9712 44.54 17.3239C44.1889 16.6766 44.0133 15.925 44.0133 15.0692C44.0133 14.2025 44.1889 13.4455 44.54 12.7982C44.902 12.1399 45.3957 11.6297 46.0211 11.2676C46.6465 10.8946 47.3597 10.7081 48.1606 10.7081C49.1699 10.7081 50.0147 10.9714 50.6949 11.498C51.3752 12.0247 51.8086 12.7378 51.9951 13.6375H50.2835C50.1738 13.1547 49.9215 12.7817 49.5265 12.5184C49.1425 12.2551 48.6817 12.1234 48.1441 12.1234C47.7052 12.1234 47.2993 12.2386 46.9263 12.469C46.5532 12.6884 46.2515 13.0176 46.0211 13.4564C45.8017 13.8843 45.692 14.4164 45.692 15.0528C45.692 15.5246 45.7578 15.947 45.8895 16.32C46.0211 16.682 46.1967 16.9892 46.4161 17.2416C46.6465 17.4939 46.9098 17.6859 47.206 17.8176C47.5023 17.9383 47.8149 17.9986 48.1441 17.9986C48.5061 17.9986 48.8298 17.9438 49.1151 17.834C49.4113 17.7134 49.6581 17.5378 49.8556 17.3074C50.0641 17.077 50.2067 16.8027 50.2835 16.4846H51.9951C51.8086 17.3623 51.3752 18.0699 50.6949 18.6075C50.0147 19.1342 49.1699 19.3975 48.1606 19.3975Z" fill="#F4F4F4"/>
<path d="M1.60439 4.69545V7.04827C1.60439 7.2077 1.64039 7.32345 1.71239 7.39545C1.78953 7.4623 1.91811 7.4957 2.09811 7.4957H2.63811V8.22859H1.94382C1.54782 8.22859 1.24439 8.13602 1.03353 7.95088C0.822678 7.76573 0.717249 7.46484 0.717249 7.04827V4.69545H0.21582V3.97802H0.717249V2.92116H1.60439V3.97802H2.63811V4.69545H1.60439ZM5.18436 3.90859C5.50836 3.90859 5.79636 3.97802 6.04836 4.11688C6.30551 4.25573 6.50608 4.46145 6.65008 4.73402C6.79922 5.00659 6.87376 5.33573 6.87376 5.72145V8.22859H6.00208V5.85259C6.00208 5.47202 5.90693 5.18145 5.71665 4.98088C5.52636 4.77516 5.26665 4.67231 4.9375 4.67231C4.60836 4.67231 4.34608 4.77516 4.15065 4.98088C3.96036 5.18145 3.86522 5.47202 3.86522 5.85259V8.22859H2.98579V2.52002H3.86522V4.47173C4.01436 4.29173 4.20208 4.15288 4.42836 4.05516C4.65979 3.95745 4.91179 3.90859 5.18436 3.90859ZM11.4284 5.99916C11.4284 6.15859 11.4181 6.30259 11.3976 6.43116H8.14981C8.17552 6.77059 8.30156 7.04313 8.52784 7.24884C8.75413 7.45456 9.03184 7.55741 9.36099 7.55741C9.83413 7.55741 10.1684 7.35945 10.3638 6.96345H11.3127C11.1841 7.3543 10.9501 7.6757 10.6107 7.9277C10.2764 8.17462 9.85984 8.29805 9.36099 8.29805C8.9547 8.29805 8.58956 8.20802 8.26556 8.02802C7.9467 7.84288 7.6947 7.58573 7.50956 7.25659C7.32956 6.92231 7.23952 6.53659 7.23952 6.09945C7.23952 5.66231 7.32695 5.27916 7.50181 4.95002C7.68181 4.61573 7.93127 4.35859 8.25013 4.17859C8.57413 3.99859 8.94442 3.90859 9.36099 3.90859C9.76213 3.90859 10.1195 3.99602 10.4332 4.17088C10.747 4.34573 10.9913 4.59259 11.1661 4.91145C11.341 5.22516 11.4284 5.58773 11.4284 5.99916ZM10.5104 5.72145C10.5052 5.39745 10.3896 5.13773 10.1633 4.94231C9.93699 4.74688 9.65667 4.64916 9.32238 4.64916C9.01895 4.64916 8.75927 4.74688 8.54327 4.94231C8.32727 5.13259 8.1987 5.3923 8.15756 5.72145H10.5104Z" fill="#ABABAB"/>
<path d="M53.3149 19.2V7.67999H57.5773C58.3783 7.67999 59.0475 7.81165 59.5851 8.07496C60.1227 8.32731 60.5232 8.67839 60.7865 9.12822C61.0608 9.56708 61.1979 10.0663 61.1979 10.6258C61.1979 11.2073 61.0717 11.6955 60.8194 12.0905C60.5671 12.4855 60.2324 12.7927 59.8155 13.0121C59.4096 13.2206 58.9707 13.3412 58.4989 13.3742L58.7293 13.2096C59.234 13.2206 59.6948 13.3577 60.1117 13.621C60.5287 13.8734 60.8578 14.2135 61.0992 14.6414C61.3405 15.0692 61.4612 15.541 61.4612 16.0567C61.4612 16.6491 61.3186 17.1867 61.0333 17.6695C60.7481 18.1412 60.3257 18.5143 59.7661 18.7886C59.2066 19.0628 58.5209 19.2 57.709 19.2H53.3149ZM54.9607 17.834H57.4951C58.2192 17.834 58.7787 17.6695 59.1737 17.3403C59.5796 17.0002 59.7826 16.523 59.7826 15.9086C59.7826 15.3051 59.5741 14.8224 59.1572 14.4603C58.7513 14.0983 58.1863 13.9172 57.4621 13.9172H54.9607V17.834ZM54.9607 12.65H57.3963C58.0875 12.65 58.6141 12.491 58.9762 12.1728C59.3383 11.8437 59.5193 11.3938 59.5193 10.8233C59.5193 10.2747 59.3383 9.84136 58.9762 9.52319C58.6141 9.19405 58.0711 9.02948 57.3469 9.02948H54.9607V12.65ZM62.025 19.2V10.9056H63.5062L63.6543 12.469C63.8408 12.096 64.0822 11.7833 64.3784 11.531C64.6746 11.2676 65.0202 11.0647 65.4152 10.922C65.8211 10.7794 66.2819 10.7081 66.7976 10.7081V12.4526H66.2051C65.865 12.4526 65.5414 12.4964 65.2342 12.5842C64.927 12.661 64.6527 12.7982 64.4113 12.9956C64.1809 13.1931 63.9999 13.4619 63.8682 13.802C63.7366 14.1422 63.6707 14.5646 63.6707 15.0692V19.2H62.025ZM70.5367 19.3975C69.7577 19.3975 69.0555 19.2164 68.4299 18.8544C67.8155 18.4923 67.3273 17.9876 66.9653 17.3403C66.6142 16.682 66.4386 15.925 66.4386 15.0692C66.4386 14.1915 66.6197 13.429 66.9817 12.7817C67.3438 12.1234 67.8375 11.6133 68.4628 11.2512C69.0884 10.8891 69.7906 10.7081 70.5696 10.7081C71.3595 10.7081 72.0617 10.8891 72.6761 11.2512C73.2905 11.6133 73.7732 12.1179 74.1243 12.7652C74.4864 13.4126 74.6674 14.1751 74.6674 15.0528C74.6674 15.9305 74.4864 16.693 74.1243 17.3403C73.7732 17.9876 73.285 18.4923 72.6596 18.8544C72.0343 19.2164 71.3266 19.3975 70.5367 19.3975ZM70.5367 17.9822C70.9865 17.9822 71.3924 17.8724 71.7545 17.653C72.1275 17.4336 72.4237 17.1099 72.6432 16.682C72.8736 16.2432 72.9888 15.7001 72.9888 15.0528C72.9888 14.4055 72.8791 13.8679 72.6596 13.44C72.4402 13.0011 72.144 12.672 71.7709 12.4526C71.4089 12.2331 71.0084 12.1234 70.5696 12.1234C70.1307 12.1234 69.7248 12.2331 69.3517 12.4526C68.9787 12.672 68.677 13.0011 68.4464 13.44C68.227 13.8679 68.1173 14.4055 68.1173 15.0528C68.1173 15.7001 68.227 16.2432 68.4464 16.682C68.677 17.1099 68.9732 17.4336 69.3353 17.653C69.7083 17.8724 70.1088 17.9822 70.5367 17.9822ZM76.6759 19.2L74.2402 10.9056H75.8695L77.6797 17.8176L77.3671 17.8011L79.3748 10.9056H81.218L83.2258 17.8011L82.9131 17.8176L84.7069 10.9056H86.3691L83.9335 19.2H82.2384L80.1319 12.0082H80.461L78.3545 19.2H76.6759ZM89.7469 19.3975C89.0448 19.3975 88.4304 19.2823 87.9037 19.0519C87.3771 18.8215 86.9602 18.4978 86.653 18.0809C86.3458 17.664 86.1593 17.1758 86.0935 16.6162H87.7721C87.8269 16.8795 87.9312 17.1209 88.0848 17.3403C88.2493 17.5598 88.4688 17.7353 88.7431 17.867C89.0283 17.9986 89.3629 18.0644 89.7469 18.0644C90.109 18.0644 90.4052 18.0151 90.6356 17.9163C90.877 17.8066 91.0525 17.664 91.1623 17.4884C91.272 17.3019 91.3268 17.1044 91.3268 16.896C91.3268 16.5888 91.25 16.3584 91.0964 16.2048C90.9538 16.0402 90.7344 15.914 90.4381 15.8263C90.1529 15.7275 89.8073 15.6398 89.4013 15.563C89.0173 15.4971 88.6443 15.4094 88.2823 15.2996C87.9312 15.179 87.613 15.0308 87.3277 14.8553C87.0535 14.6798 86.834 14.4603 86.6695 14.197C86.5049 13.9227 86.4226 13.5881 86.4226 13.1931C86.4226 12.7214 86.5488 12.299 86.8011 11.9259C87.0535 11.5419 87.41 11.2457 87.8708 11.0373C88.3426 10.8178 88.8967 10.7081 89.533 10.7081C90.4546 10.7081 91.1952 10.9275 91.7547 11.3664C92.3143 11.8052 92.6434 12.4251 92.7421 13.226H91.1458C91.1019 12.853 90.9373 12.5678 90.6521 12.3703C90.3668 12.1618 89.9883 12.0576 89.5165 12.0576C89.0448 12.0576 88.6827 12.1509 88.4304 12.3374C88.178 12.5239 88.0519 12.7707 88.0519 13.0779C88.0519 13.2754 88.1232 13.451 88.2658 13.6046C88.4084 13.7582 88.6169 13.8898 88.8912 13.9995C89.1764 14.0983 89.522 14.1915 89.928 14.2793C90.5095 14.389 91.0306 14.5262 91.4914 14.6907C91.9522 14.8553 92.3197 15.0967 92.594 15.4148C92.8683 15.733 93.0055 16.1883 93.0055 16.7808C93.0164 17.2964 92.8848 17.7518 92.6105 18.1467C92.3472 18.5417 91.9687 18.8489 91.4749 19.0683C90.9922 19.2878 90.4162 19.3975 89.7469 19.3975ZM97.3789 19.3975C96.589 19.3975 95.8868 19.2164 95.2724 18.8544C94.658 18.4923 94.1753 17.9876 93.8242 17.3403C93.4841 16.693 93.314 15.9415 93.314 15.0857C93.314 14.208 93.4841 13.4455 93.8242 12.7982C94.1753 12.1399 94.658 11.6297 95.2724 11.2676C95.8868 10.8946 96.6 10.7081 97.4119 10.7081C98.2237 10.7081 98.9204 10.8891 99.5019 11.2512C100.083 11.6133 100.533 12.096 100.851 12.6994C101.17 13.2919 101.329 13.9502 101.329 14.6743C101.329 14.784 101.323 14.9047 101.312 15.0363C101.312 15.157 101.307 15.2942 101.296 15.4478H94.5154V14.2793H99.6829C99.65 13.5881 99.4196 13.0505 98.9917 12.6665C98.5639 12.2715 98.0317 12.074 97.3954 12.074C96.9456 12.074 96.5341 12.1783 96.1611 12.3867C95.7881 12.5842 95.4864 12.8805 95.256 13.2754C95.0365 13.6594 94.9268 14.1476 94.9268 14.7401V15.2009C94.9268 15.8153 95.0365 16.3364 95.256 16.7643C95.4864 17.1812 95.7881 17.4994 96.1611 17.7188C96.5341 17.9273 96.9401 18.0315 97.3789 18.0315C97.9056 18.0315 98.3389 17.9163 98.6791 17.6859C99.0192 17.4555 99.2715 17.1428 99.4361 16.7479H101.082C100.939 17.2526 100.698 17.7079 100.358 18.1138C100.018 18.5088 99.5952 18.8215 99.0905 19.0519C98.5968 19.2823 98.0263 19.3975 97.3789 19.3975ZM101.84 19.2V10.9056H103.321L103.469 12.469C103.656 12.096 103.897 11.7833 104.194 11.531C104.49 11.2676 104.835 11.0647 105.23 10.922C105.636 10.7794 106.097 10.7081 106.613 10.7081V12.4526H106.02C105.68 12.4526 105.357 12.4964 105.049 12.5842C104.742 12.661 104.468 12.7982 104.226 12.9956C103.996 13.1931 103.815 13.4619 103.683 13.802C103.552 14.1422 103.486 14.5646 103.486 15.0692V19.2H101.84Z" fill="#F4F4F4"/>
</svg>
          `,
    collapsed: `<svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M5.37468 11.8891L26.0102 6.1111C26.5109 5.97093 26.9721 6.43222 26.832 6.93284L21.054 27.5683C20.8852 28.1711 20.0539 28.2301 19.8018 27.6571L15.4708 17.8139C15.4037 17.6613 15.2817 17.5394 15.1291 17.4722L5.28594 13.1413C4.71301 12.8892 4.77193 12.0578 5.37468 11.8891Z" fill="#121212" stroke="#121212" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
`,
    inputSend: `<svg width="14" height="14" style="margin-top: 2px;height:20px;width:20px;" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
<path fill-rule="evenodd" clip-rule="evenodd" d="M1.91978 1.93011C1.75435 1.86045 1.56314 1.89892 1.43751 2.02714C1.31188 2.15537 1.27732 2.34732 1.35035 2.5113L3.15439 6.56248H7.58333C7.82495 6.56248 8.02083 6.75836 8.02083 6.99998C8.02083 7.2416 7.82495 7.43748 7.58333 7.43748H3.1544L1.35035 11.4887C1.27732 11.6526 1.31188 11.8446 1.43751 11.9728C1.56314 12.1011 1.75435 12.1396 1.91978 12.0698L13.0031 7.40324C13.1654 7.33493 13.2708 7.17603 13.2708 6.99998C13.2708 6.82399 13.1654 6.66509 13.0031 6.59678L1.91978 1.93011Z" fill="#999999"/>
</svg>
`,
  };

  const wrapper = document.createElement("div");
  wrapper.innerHTML = icons[type] || "";
  return wrapper.firstChild;
}

function removeOverlay() {
  const wrapper = document.getElementById("tawebagent-overlay-wrapper");
  if (wrapper) {
    wrapper.remove();
  }
}

function enableOverlay() {
  const input = document.getElementById("tawebagent-user-input");
  if (input) {
    input.placeholder = "What can I help you solve today?";
    input.disabled = false;
  }
}

function disableOverlay() {
  const input = document.getElementById("tawebagent-user-input");
  if (input) {
    input.placeholder = "Processing...";
    input.disabled = true;
  }
}

function isDisabled() {
  const input = document.getElementById("tawebagent-user-input");
  return input ? input.disabled : true;
}

function showExpandedOverlay(processing_state = "init", show_steps = true) {
  removeOverlay();
  window.overlay_state_changed(false);
  show_details = show_steps;

  // Create wrapper
  const wrapper = document.createElement("div");
  wrapper.id = "tawebagent-overlay-wrapper";
  wrapper.className = "tawebagent-overlay-wrapper";

  // Create main container
  const expandedOverlay = document.createElement("div");
  expandedOverlay.id = "tawebagent-overlay";
  expandedOverlay.className = "tawebagent-chat-container";
  expandedOverlay.style.position = "fixed";
  expandedOverlay.style.right = "24px";
  expandedOverlay.style.bottom = "24px";

  // Create header
  const header = createHeader();

  // Create progress bar
  const progressBar = document.createElement("div");
  progressBar.id = "tawebagentExpandedAnimation";
  progressBar.style.height = "2px";
  progressBar.style.width = "100%";

  // Create messages container
  const messagesContainer = document.createElement("div");
  messagesContainer.id = "tawebagent-chat-box";
  messagesContainer.className = "tawebagent-chat-messages";

  // Create settings bar
  // const settingsBar = createSettingsBar();

  // Create input section
  const inputSection = createInputSection();

  // Create disclaimer
  const disclaimer = createDisclaimer();

  // Assembly
  expandedOverlay.appendChild(header);
  expandedOverlay.appendChild(progressBar);
  expandedOverlay.appendChild(messagesContainer);
  // expandedOverlay.appendChild(settingsBar);
  expandedOverlay.appendChild(inputSection);
  expandedOverlay.appendChild(disclaimer);

  wrapper.appendChild(expandedOverlay);
  document.body.appendChild(wrapper);
  updateOverlayState(processing_state, false);
  setupEventListeners();
  setupScrollCheck();
  focusOnOverlayInput();

  setInterval(maintainScroll, 100);
}

function createHeader() {
  const header = document.createElement("div");
  header.className = "tawebagent-chat-header";

  const logoContainer = document.createElement("div");
  logoContainer.className = "tawebagent-logo-container";

  // Create logo
  const logo = createSvgIcon("logo");

  logoContainer.appendChild(logo);

  const closeButton = document.createElement("button");
  closeButton.innerHTML = createSvgIcon("minimize").outerHTML;
  closeButton.className = "tawebagent-send-button";
  closeButton.style.position = "static";
  closeButton.onclick = () => {
    const currentState = document.getElementById(
      "tawebagentExpandedAnimation"
    ).className;
    const state = currentState.includes("processingLine")
      ? "processing"
      : currentState.includes("doneStateLine")
      ? "done"
      : "init";
    showCollapsedOverlay(state, show_details);
  };

  header.appendChild(logoContainer);
  header.appendChild(closeButton);
  return header;
}

function createSettingsBar() {
  const settingsBar = document.createElement("div");
  settingsBar.className = "tawebagent-settings-bar";

  const toggleContainer = document.createElement("div");
  toggleContainer.className = "tawebagent-toggle-container";

  const label = document.createElement("span");
  label.textContent = "Show Details";
  label.style.color = "white";
  label.style.fontSize = "13px";

  const toggle = document.createElement("div");
  toggle.className = `tawebagent-toggle ${
    show_details ? "tawebagent-toggle-checked" : ""
  }`;
  const thumb = document.createElement("div");
  thumb.className = "tawebagent-toggle-thumb";
  toggle.appendChild(thumb);

  toggle.onclick = () => {
    show_details = !show_details;
    toggle.classList.toggle("tawebagent-toggle-checked");

    // Update only step messages visibility
    const chatBox = document.getElementById("tawebagent-chat-box");
    if (chatBox) {
      const messages = chatBox.getElementsByTagName("div");
      Array.from(messages).forEach((msg) => {
        // Only toggle visibility for step messages
        if (msg.getAttribute("data-message-type") === "step") {
          msg.style.display = show_details ? "flex" : "none";
        }
      });
    }

    window.show_steps_state_changed(show_details);
  };

  toggleContainer.appendChild(label);
  toggleContainer.appendChild(toggle);
  settingsBar.appendChild(toggleContainer);

  return settingsBar;
}

function createInputSection() {
  const settingsBar = createSettingsBar();
  const inputContainer = document.createElement("div");
  inputContainer.className = "tawebagent-input-container";

  const inputWrapper = document.createElement("div");
  inputWrapper.className = "tawebagent-input-wrapper";

  const textarea = document.createElement("textarea");
  textarea.id = "tawebagent-user-input";
  textarea.className = "tawebagent-textarea";
  textarea.placeholder = "What can I help you solve today?";
  textarea.rows = 1; // Changed from 3 to 1 for better initial height

  const sendButton = document.createElement("button");
  sendButton.id = "tawebagent-send-btn";
  sendButton.className =
    "tawebagent-send-button tawebagent-send-button-disabled";
  sendButton.innerHTML = createSvgIcon("inputSend").outerHTML;
  sendButton.type = "button"; // Add this to prevent form submission

  inputWrapper.appendChild(textarea);
  inputWrapper.appendChild(sendButton);
  inputContainer.appendChild(settingsBar);
  inputContainer.appendChild(inputWrapper);

  // Add auto-resize functionality
  textarea.addEventListener("input", function () {
    // Reset height temporarily to get the correct scrollHeight
    this.style.height = "28px";
    // Set new height
    this.style.height = Math.min(this.scrollHeight - 8, 200) + "px";
  });

  return inputContainer;
}

function createDisclaimer() {
  const disclaimer = document.createElement("div");
  disclaimer.className = "tawebagent-disclaimer";

  const text = document.createElement("span");
  text.textContent =
    "TheAgentic Browser can make mistakes. Verify important info.";

  disclaimer.appendChild(text);

  return disclaimer;
}

function setupEventListeners() {
  const textarea = document.getElementById("tawebagent-user-input");
  const sendButton = document.getElementById("tawebagent-send-btn");

  textarea.addEventListener("input", (e) => {
    const hasText = e.target.value.trim().length > 0;
    sendButton.className = `tawebagent-send-button ${
      hasText
        ? "tawebagent-send-button-enabled"
        : "tawebagent-send-button-disabled"
    }`;
  });

  textarea.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendButton.click();
    }
  });

  sendButton.addEventListener("click", () => {
    const text = textarea.value.trim();
    if (text && !isDisabled()) {
      if (awaitingUserResponse) {
        addUserMessage(text);
        textarea.value = "";
      } else {
        clearOverlayMessages();
        addUserMessage(text);
        disableOverlay();
        window.process_task(text);
        textarea.value = "";
      }
      sendButton.className =
        "tawebagent-send-button tawebagent-send-button-disabled";
    }
  });
}

function addMessage(message, sender, message_type = "plan") {
  const chatBox = document.getElementById("tawebagent-chat-box");
  if (!chatBox) return;

  // Create message container with proper styling
  const messageContainer = document.createElement("div");
  messageContainer.style.width = "100%";
  messageContainer.style.display =
    sender === "user" || message_type !== "step" || show_details
      ? "flex"
      : "none";
  messageContainer.style.justifyContent =
    sender === "user" ? "flex-end" : "flex-start";
  messageContainer.style.minHeight = "min-content";
  messageContainer.setAttribute("data-message-type", message_type);

  // Create message bubble
  const messageBubble = document.createElement("div");

  // Special styling for user query messages
  if (message_type === "user_query") {
    messageBubble.className = "tawebagent-message tawebagent-user-message";
    messageBubble.style.background = "rgba(57, 181, 82, 1)"; // Green background
    messageBubble.style.color = "white";
    messageContainer.style.justifyContent = "flex-end";
  } else {
    messageBubble.className = `tawebagent-message ${
      sender === "user"
        ? "tawebagent-user-message"
        : "tawebagent-system-message"
    }`;
  }

  const cleanMessage = message.replace(/^"|"$/g, "");
  messageBubble.innerHTML = cleanMessage;

  messageContainer.appendChild(messageBubble);
  chatBox.appendChild(messageContainer);

  // Ensure proper scrolling
  setTimeout(() => {
    chatBox.scrollTop = chatBox.scrollHeight;
  }, 100);
}

function setupScrollCheck() {
  const chatBox = document.getElementById("tawebagent-chat-box");
  if (!chatBox) return;

  // Force recalculation of scroll heights
  function refreshScroll() {
    chatBox.style.display = "none";
    chatBox.offsetHeight; // Force reflow
    chatBox.style.display = "flex";

    const lastMessage = chatBox.lastElementChild;
    if (lastMessage) {
      lastMessage.scrollIntoView({
        behavior: "auto",
        block: "end",
        inline: "nearest",
      });
    }
  }

  // Initial refresh
  setTimeout(refreshScroll, 100);

  // Periodic check for first few seconds
  let checks = 0;
  const interval = setInterval(() => {
    refreshScroll();
    checks++;
    if (checks >= 5) clearInterval(interval);
  }, 1000);
}

function addSystemMessage(
  message,
  is_awaiting_user_response = false,
  message_type = "plan"
) {
  awaitingUserResponse = is_awaiting_user_response;

  // Add loading indicator if processing
  if (message_type === "processing") {
    addLoadingIndicator();
  }

  requestAnimationFrame(() => {
    addMessage(message, "system", message_type);
  });
}

function addLoadingIndicator() {
  const chatBox = document.getElementById("tawebagent-chat-box");
  if (!chatBox) return;

  const loadingContainer = document.createElement("div");
  loadingContainer.className = "tawebagent-message tawebagent-system-message";
  loadingContainer.style.display = "flex";
  loadingContainer.style.gap = "4px";
  loadingContainer.style.padding = "8px 16px";

  // Create bouncing dots
  for (let i = 0; i < 3; i++) {
    const dot = document.createElement("div");
    dot.style.width = "8px";
    dot.style.height = "8px";
    dot.style.borderRadius = "50%";
    dot.style.background = "#9333EA";
    dot.style.animation = "bounce 1.4s infinite ease-in-out";
    dot.style.animationDelay = `${i * 0.16}s`;
    loadingContainer.appendChild(dot);
  }

  chatBox.appendChild(loadingContainer);
}

function addUserMessage(message) {
  requestAnimationFrame(() => {
    addMessage(message, "user", "user");
  });
}

function clearOverlayMessages() {
  const chatBox = document.getElementById("tawebagent-chat-box");
  if (!chatBox) return;

  while (chatBox.firstChild) {
    chatBox.removeChild(chatBox.firstChild);
  }
}

function focusOnOverlayInput() {
  const input = document.getElementById("tawebagent-user-input");
  if (input) {
    requestAnimationFrame(() => {
      input.focus();
    });
  }
}

function maintainScroll() {
  const chatBox = document.getElementById("tawebagent-chat-box");
  if (!chatBox) return;

  const shouldScroll =
    chatBox.scrollHeight - chatBox.clientHeight <= chatBox.scrollTop + 1;

  if (shouldScroll) {
    chatBox.scrollTop = chatBox.scrollHeight;
  }
}

// Add these keyframe animations to the existing styles
function addKeyframeAnimations() {
  const style = document.createElement("style");
  style.textContent = `
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }

    @keyframes fadeOut {
      from { opacity: 1; transform: translateY(0); }
      to { opacity: 0; transform: translateY(-10px); }
    }

    @keyframes bounce {
      0%, 80%, 100% { transform: translateY(0); }
      40% { transform: translateY(-6px); }
    }

    @keyframes gradient {
      0% { background-position: 0% 50%; }
      50% { background-position: 100% 50%; }
      100% { background-position: 0% 50%; }
    }
  `;
  document.head.appendChild(style);
}

// Initialize
function init() {
  injectOveralyStyles();
  addKeyframeAnimations();
  // Start with collapsed view
  showCollapsedOverlay("init");
}

// Call initialization
init();
