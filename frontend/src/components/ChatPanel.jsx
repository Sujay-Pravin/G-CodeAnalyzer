import React, { useEffect, useRef, useState } from 'react';
import { docco } from 'react-syntax-highlighter/dist/cjs/styles/hljs';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

function ChatPanel({ 
  chatHistory, 
  chatQuery, 
  setChatQuery, 
  handleChatQuerySubmit, 
  isChatLoading,
  isFileDataLoading,
  selectedFile
}) {
  const chatEndRef = useRef(null);
  const chatInputRef = useRef(null);
  const [inputHeight, setInputHeight] = useState('40px');
  
  // Scroll to bottom whenever chat history changes
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory, isChatLoading]);

  // Focus input when file is selected
  useEffect(() => {
    if (selectedFile && !isFileDataLoading && chatInputRef.current) {
      chatInputRef.current.focus();
    }
  }, [selectedFile, isFileDataLoading]);

  // Format message with code highlighting
  const formatMessage = (text) => {
    if (!text) return '';
    
    // Use marked to parse markdown
    const renderer = new marked.Renderer();
    
    // Customize code block rendering to include syntax highlighting
    renderer.code = (code, language) => {
      return `<pre class="code-block ${language || ''}"><code>${code}</code></pre>`;
    };
    
    // Convert markdown to HTML
    const rawHtml = marked(text, { renderer });
    
    // Sanitize HTML to prevent XSS
    const cleanHtml = DOMPurify.sanitize(rawHtml);
    
    return <div dangerouslySetInnerHTML={{ __html: cleanHtml }} />;
  };

  // Format timestamp
  const formatTime = (date) => {
    return new Date(date || Date.now()).toLocaleTimeString([], { 
      hour: '2-digit', 
      minute: '2-digit' 
    });
  };

  // Handle input resize
  const handleInputChange = (e) => {
    setChatQuery(e.target.value);
    
    // Auto-resize input
    e.target.style.height = 'auto';
    const newHeight = Math.min(120, Math.max(40, e.target.scrollHeight));
    e.target.style.height = `${newHeight}px`;
    setInputHeight(`${newHeight}px`);
  };

  // Handle key press
  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleChatQuerySubmit(e);
    }
  };

  return (
    <div className="chat-panel">
      <div className="chat-panel-header">
        <h3>
          {selectedFile ? (
            <>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ marginRight: '8px' }}>
                <path d="M14 2H6C5.46957 2 4.96086 2.21071 4.58579 2.58579C4.21071 2.96086 4 3.46957 4 4V20C4 20.5304 4.21071 21.0391 4.58579 21.4142C4.96086 21.7893 5.46957 22 6 22H18C18.5304 22 19.0391 21.7893 19.4142 21.4142C19.7893 21.0391 20 20.5304 20 20V8L14 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M14 2V8H20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              {selectedFile.path}
            </>
          ) : (
            'Chat'
          )}
        </h3>
      </div>
      
      <div className="chat-history">
        {isFileDataLoading && selectedFile ? (
          <div className="loading-container">
            <div className="spinner">
              <div className="bounce1"></div>
              <div className="bounce2"></div>
              <div className="bounce3"></div>
            </div>
            <p>Loading file data...</p>
          </div>
        ) : chatHistory.length === 0 ? (
          <div className="chat-empty-state">
            {selectedFile ? (
              <>
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M8 10H16M8 14H12M21 12C21 16.9706 16.9706 21 12 21C7.02944 21 3 16.9706 3 12C3 7.02944 7.02944 3 12 3C16.9706 3 21 7.02944 21 12Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                <h3>Ask about this file</h3>
                <p>Chat with AI about the code structure, functions, and relationships in <strong>{selectedFile.path}</strong></p>
              </>
            ) : (
              <>
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M7 14L5 12M5 12L7 10M5 12H15M13 18L15 20M15 20L17 18M15 20V12M9 6L7 4M7 4L5 6M7 4V12M19 14L21 12M21 12L19 10M21 12H11" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                <h3>Select a file to begin</h3>
                <p>Choose a file from the left panel to view its graph and chat about it</p>
              </>
            )}
          </div>
        ) : (
          chatHistory.map((msg, index) => (
            <div 
              key={index} 
              className={`chat-message ${msg.sender === 'user' ? 'user-message' : 'ai-message'}`}
            >
              <div className="message-header">
                <span className="message-sender">{msg.sender === 'user' ? 'You' : 'AI'}</span>
              </div>
              <div className="message-content">
                {typeof msg.text === 'string' ? formatMessage(msg.text) : msg.text}
              </div>
              <span className="message-time">
                {formatTime(msg.timestamp)}
              </span>
            </div>
          ))
        )}
        
        {isChatLoading && (
          <div className="chat-message ai-message">
            <div className="message-header">
              <span className="message-sender">AI</span>
            </div>
            <div className="typing">
              <span></span>
              <span></span>
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        )}
        
        <div ref={chatEndRef} />
      </div>
      
      <div className="chat-input-container">
        <form onSubmit={handleChatQuerySubmit} className="chat-form">
          <textarea
            ref={chatInputRef}
            className="chat-input"
            value={chatQuery}
            onChange={handleInputChange}
            onKeyPress={handleKeyPress}
            placeholder={selectedFile ? "Ask about this file's code structure..." : "Select a file to start chatting..."}
            disabled={isChatLoading || !selectedFile || isFileDataLoading}
            rows={1}
            style={{ height: inputHeight }}
          />
          <button 
            type="submit" 
            className="chat-submit-btn"
            disabled={isChatLoading || !chatQuery.trim() || !selectedFile || isFileDataLoading}
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M22 2L11 13M22 2L15 22L11 13M22 2L2 9L11 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </form>
      </div>
    </div>
  );
}

export default ChatPanel; 