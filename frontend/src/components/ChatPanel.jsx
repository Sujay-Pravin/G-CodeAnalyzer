import React, { useEffect, useRef, useState } from 'react';
import { docco } from 'react-syntax-highlighter/dist/cjs/styles/hljs';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import SyntaxHighlighter from 'react-syntax-highlighter';

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

  // Format message with code highlighting and structured AI output
  const formatMessage = (text) => {
    if (!text) return '';
    
    // Check if it's a structured AI response by looking for code block followed by [File] → [Entity] pattern
    const structuredResponseRegex = /```(\w+)?\s+([\s\S]+?)\s+```\s*\n\s*\[([^\]]+)\]\s*→\s*\[([^\]]+)\]/;
    const structuredMatch = text.match(structuredResponseRegex);
    
    if (structuredMatch) {
      // Extract parts of the structured response
      const language = structuredMatch[1] || '';
      const codeSnippet = structuredMatch[2];
      const fileName = structuredMatch[3];
      const entityName = structuredMatch[4];
      
      // Extract the sections (Purpose, Implementation, Relationships)
      const sectionsText = text.substring(structuredMatch[0].length);
      
      // Process the remaining content as regular markdown
      const processedSections = marked(sectionsText);
      
      return (
        <div className="structured-ai-response">
          {/* Code snippet with syntax highlighting */}
          <div className="code-snippet">
            <SyntaxHighlighter 
              language={language} 
              style={docco}
              wrapLines={true}
              showLineNumbers={true}
            >
              {String(codeSnippet)}
            </SyntaxHighlighter>
          </div>
          
          {/* File and Entity reference */}
          <div className="entity-reference">
            <span className="file-name">{fileName}</span>
            <span className="arrow">→</span>
            <span className="entity-name">{entityName}</span>
          </div>
          
          {/* Sections with details */}
          <div 
            className="response-sections"
            dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(processedSections) }}
          />
        </div>
      );
    }
    
    // Handle regular code blocks with SyntaxHighlighter for non-structured responses
    const codeBlockRegex = /```(\w+)?\n([\s\S]+?)\n```/g;
    let lastIndex = 0;
    const parts = [];
    let match;
    
    while ((match = codeBlockRegex.exec(text)) !== null) {
      // Add text before code block
      if (match.index > lastIndex) {
        const textBeforeCode = text.substring(lastIndex, match.index);
        parts.push(
          <div 
            key={`text-${lastIndex}`}
            dangerouslySetInnerHTML={{ 
              __html: DOMPurify.sanitize(marked(textBeforeCode)) 
            }}
          />
        );
      }
      
      // Add code block with syntax highlighting
      const language = match[1] || '';
      const code = match[2];
      parts.push(
        <div className="code-snippet" key={`code-${match.index}`}>
          <SyntaxHighlighter 
            language={language} 
            style={docco}
            wrapLines={true}
            showLineNumbers={true}
          >
            {String(code)}
          </SyntaxHighlighter>
        </div>
      );
      
      lastIndex = match.index + match[0].length;
    }
    
    // Add any remaining text after last code block
    if (lastIndex < text.length) {
      const remainingText = text.substring(lastIndex);
      parts.push(
        <div 
          key={`text-end`}
          dangerouslySetInnerHTML={{ 
            __html: DOMPurify.sanitize(marked(remainingText)) 
          }}
        />
      );
    }
    
    // If we parsed any code blocks, return the parts array
    if (parts.length > 0) {
      return <>{parts}</>;
    }
    
    // Otherwise use marked to parse markdown
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
            selectedFile.isRepoContext ? (
              <>
                <svg className="repo-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ marginRight: '8px' }}>
                  <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  <path d="M2 17L12 22L22 17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  <path d="M2 12L12 17L22 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                Repo Context
              </>
            ) : (
              <>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ marginRight: '8px' }}>
                  <path d="M14 2H6C5.46957 2 4.96086 2.21071 4.58579 2.58579C4.21071 2.96086 4 3.46957 4 4V20C4 20.5304 4.21071 21.0391 4.58579 21.4142C4.96086 21.7893 5.46957 22 6 22H18C18.5304 22 19.0391 21.7893 19.4142 21.4142C19.7893 21.0391 20 20.5304 20 20V8L14 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  <path d="M14 2V8H20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                {selectedFile.path}
              </>
            )
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
              selectedFile.isRepoContext ? (
                <>
                  <svg width="64" height="64" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    <path d="M2 17L12 22L22 17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    <path d="M2 12L12 17L22 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  <h3>Ask about the repository</h3>
                  <p>Chat with AI about the overall repository structure, code relationships, and architecture</p>
                </>
              ) : (
                <>
                  <svg width="64" height="64" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M8 10H16M8 14H12M21 12C21 16.9706 16.9706 21 12 21C7.02944 21 3 16.9706 3 12C3 7.02944 7.02944 3 12 3C16.9706 3 21 7.02944 21 12Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  <h3>Ask about this file</h3>
                  <p>Chat with AI about the code structure, functions, and relationships in <strong>{selectedFile.path}</strong></p>
                </>
              )
            ) : (
              <>
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M7 14L5 12M5 12L7 10M5 12H15M13 18L15 20M15 20L17 18M15 20V12M9 6L7 4M7 4L5 6M7 4V12M19 14L21 12M21 12L19 10M21 12H11" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                <h3>Select a file or repo context to begin</h3>
                <p>Choose a file from the left panel or select "Repo Context" to chat about the entire codebase</p>
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
            placeholder={selectedFile 
              ? selectedFile.isRepoContext
                ? "Ask about the repository's code structure, architecture, and relationships..."
                : "Ask about this file's code structure..." 
              : "Select a file or repo context to start chatting..."
            }
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