import React, { useState, useEffect, useRef, useContext } from 'react';
import axios from 'axios';
import { ThemeContext } from './ThemeContext';
import ThemeToggle from './components/ThemeToggle';
import './App.css';

const API_STATUS = {
  IDLE: 'idle',
  FETCHING: 'fetching',
  PROCESSING: 'processing',
  READY: 'ready',
  ERROR: 'error',
};

function App() {
  const { theme } = useContext(ThemeContext);
  const [githubUrl, setGithubUrl] = useState('');
  const [uiState, setUiState] = useState('welcome'); // welcome, loading, file-selection, chat
  const [statusMessage, setStatusMessage] = useState('');
  const [apiState, setApiState] = useState(API_STATUS.IDLE);
  
  // State for file selection
  const [files, setFiles] = useState([]);
  const [selectedFiles, setSelectedFiles] = useState(new Set());
  const [repoId, setRepoId] = useState(null);

  const [chatQuery, setChatQuery] = useState('');
  const [chatHistory, setChatHistory] = useState([]);
  const [isChatLoading, setIsChatLoading] = useState(false);
  const chatEndRef = useRef(null);
  const [fileSearchTerm, setFileSearchTerm] = useState('');
  const [isHeaderVisible, setIsHeaderVisible] = useState(true);
  const prevScrollPos = useRef(0);
  
  // State for the confirmation dialog
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [isClearing, setIsClearing] = useState(false);

  const [processingProgress, setProcessingProgress] = useState({
    total: 0,
    processed: 0,
    percentage: 0,
    currentFile: ''
  });

  const BACKEND_BASE_URL = 'http://localhost:5000/api';
  const RAG_API_URL = 'http://localhost:5001/api/chat';
  const CLEAR_DB_URL = 'http://localhost:5001/api/clear-database';

  // Scroll to bottom whenever chat history changes
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory]);

  // Handle scroll in chat history to hide/show header
  useEffect(() => {
    const handleScroll = (e) => {
      if (!e.target.classList.contains('chat-history')) return;
      
      const currentScrollPos = e.target.scrollTop;
      const isScrollingDown = currentScrollPos > prevScrollPos.current && currentScrollPos > 50;
      
      if (isScrollingDown !== !isHeaderVisible) {
        setIsHeaderVisible(!isScrollingDown);
      }
      
      prevScrollPos.current = currentScrollPos;
    };
    
    const chatHistory = document.querySelector('.chat-history');
    if (chatHistory) {
      chatHistory.addEventListener('scroll', handleScroll);
    }
    
    return () => {
      const chatHistory = document.querySelector('.chat-history');
      if (chatHistory) {
        chatHistory.removeEventListener('scroll', handleScroll);
      }
    };
  }, [isHeaderVisible]);

  // Handle the "Start New" button click
  const handleStartNewClick = () => {
    setShowConfirmDialog(true);
  };

  // Handle confirmation dialog confirmation
  const handleConfirmStartNew = async () => {
    setIsClearing(true);
    try {
      await axios.post(CLEAR_DB_URL);
      
      // Reset all state
      setGithubUrl('');
      setUiState('welcome');
      setStatusMessage('');
      setApiState(API_STATUS.IDLE);
      setFiles([]);
      setSelectedFiles(new Set());
      setRepoId(null);
      setChatHistory([]);
      setChatQuery('');
    } catch (error) {
      console.error('Error clearing database:', error);
      setChatHistory(prev => [...prev, { 
        sender: 'ai', 
        text: `Error clearing database: ${error.message}. Please try again.` 
      }]);
    } finally {
      setShowConfirmDialog(false);
      setIsClearing(false);
    }
  };

  // Handle confirmation dialog cancellation
  const handleCancelStartNew = () => {
    setShowConfirmDialog(false);
  };

  const handleSubmitRepo = async (e) => {
    e.preventDefault();
    if (!githubUrl.trim()) return;

    setUiState('loading');
    setApiState(API_STATUS.FETCHING);
    setStatusMessage('Fetching repository files...');
    setChatHistory([]);
    setFiles([]);
    setSelectedFiles(new Set());

    try {
      const fetchResponse = await axios.post(`${BACKEND_BASE_URL}/fetch-repo-files`, {
        github_url: githubUrl,
      });

      if (!fetchResponse.data.success) {
        throw new Error(fetchResponse.data.message || 'Failed to fetch files.');
      }
      
      setFiles(fetchResponse.data.files);
      setRepoId(fetchResponse.data.repo_id);
      setStatusMessage('Please select files to process.');
      setApiState(API_STATUS.IDLE);
      setUiState('file-selection');

    } catch (error) {
      console.error('Error fetching repository:', error);
      setStatusMessage(`Error: ${error.message}`);
      setApiState(API_STATUS.ERROR);
      setUiState('welcome'); // Revert to welcome on error
    }
  };

  const handleFileSelect = (filePath) => {
    const newSelectedFiles = new Set(selectedFiles);
    if (newSelectedFiles.has(filePath)) {
      newSelectedFiles.delete(filePath);
    } else {
      newSelectedFiles.add(filePath);
    }
    setSelectedFiles(newSelectedFiles);
  };

  const handleSelectAll = () => {
    if (selectedFiles.size === filteredFiles.length) {
      setSelectedFiles(new Set()); // Deselect all
    } else {
      setSelectedFiles(new Set(filteredFiles)); // Select all filtered files
    }
  };
  
  const handleProcessSelectedFiles = async () => {
    if (selectedFiles.size === 0) {
      setStatusMessage('Please select at least one file.');
      return;
    }

    setUiState('loading');
    setApiState(API_STATUS.PROCESSING);
    setStatusMessage(`Processing ${selectedFiles.size} selected files...`);
    
    // Initialize progress with known values
    setProcessingProgress({
      total: selectedFiles.size,
      processed: 0,
      percentage: 0,
      currentFile: ''
    });

    try {
      const processResponse = await axios.post(`${BACKEND_BASE_URL}/process-files`, {
        selected_files: Array.from(selectedFiles),
        repo_id: repoId,
      });

      if (!processResponse.data.success) {
        throw new Error(processResponse.data.message || 'Failed to process files.');
      }

      // Start polling for status
      pollProcessingStatus(repoId);

    } catch (error) {
      console.error('Error processing files:', error);
      setStatusMessage(`Error: ${error.message}`);
      setApiState(API_STATUS.ERROR);
      setUiState('file-selection'); // Go back to selection on error
    }
  };

  // New function to poll processing status
  const pollProcessingStatus = async (repoId) => {
    if (!repoId) return;
    
    // Use a variable to track if we should continue polling
    let continuePolling = true;
    let pollCount = 0;
    const MAX_POLLS = 120; // Maximum number of polls (10 minutes at 5s intervals)
    
    while (continuePolling && pollCount < MAX_POLLS) {
      try {
        // Poll the status endpoint
        const statusResponse = await axios.get(`${BACKEND_BASE_URL}/processing-status?repo_id=${repoId}`);
        
        if (statusResponse.data.success) {
          // Extract the relevant data from the response
          const { status, message, is_complete, files_processed, total_files, partial_success } = statusResponse.data;
          
          // Update progress state
          const percentage = total_files > 0 
            ? Math.round((files_processed / total_files) * 100) 
            : 0;
            
          setProcessingProgress({
            total: total_files || 0,
            processed: files_processed || 0,
            percentage: percentage,
            currentFile: statusResponse.data.current_file || ''
          });
          
          // Update UI with current status
          setStatusMessage(`${message} (${files_processed || 0}/${total_files || 0})`);
          
          // Check if processing is complete, partial success, or had an error
          if (is_complete === true) {
            // Set progress to 100% when complete
            setProcessingProgress(prev => ({
              ...prev, 
              percentage: 100,
              processed: prev.total
            }));
            
            setApiState(API_STATUS.READY);
            
            // Customize message based on complete vs partial
            if (partial_success) {
              setStatusMessage(`Partial processing complete. ${files_processed}/${total_files} files analyzed.`);
              
              // If there are failed files, add them to the message
              if (statusResponse.data.failed_files && statusResponse.data.failed_files.length > 0) {
                console.log("Failed files:", statusResponse.data.failed_files);
              }
            } else {
              setStatusMessage(`Processing complete! ${total_files} files analyzed.`);
            }
            
            setChatHistory([
              { 
                sender: 'ai', 
                text: partial_success 
                  ? `I've analyzed ${files_processed} out of ${total_files} selected files from your codebase. Some files couldn't be processed, but we can still work with what we have. What would you like to know about the code structure, functions, or relationships?`
                  : `I've analyzed all ${total_files} selected files from your codebase. What would you like to know about the code structure, functions, relationships between components, or any specific implementation details?`
              }
            ]);
            setUiState('chat');
            continuePolling = false;
          } else if (status === 'error') {
            setApiState(API_STATUS.ERROR);
            setStatusMessage(`Error: ${message}`);
            continuePolling = false;
          }
        }
      } catch (error) {
        console.error('Error polling status:', error);
        // Don't stop polling on error, just continue
      }
      
      // Increment poll count
      pollCount++;
      
      // Wait 5 seconds before next poll if we're still polling
      if (continuePolling) {
        await new Promise(resolve => setTimeout(resolve, 5000));
      }
    }
    
    // If we reached max polls without completing
    if (pollCount >= MAX_POLLS && continuePolling) {
      setApiState(API_STATUS.ERROR);
      setStatusMessage('Processing timed out. Please try again or with fewer files.');
      setUiState('file-selection');
    }
  };

  const handleChatQuerySubmit = async (e) => {
    e.preventDefault();
    if (!chatQuery.trim() || isChatLoading) return;

    const userMessage = { sender: 'user', text: chatQuery };
    setChatHistory((prev) => [...prev, userMessage]);
    setChatQuery('');

    setIsChatLoading(true);

    try {
      const response = await axios.post(RAG_API_URL, { query: chatQuery });
      const aiMessage = { sender: 'ai', text: response.data.response };
      setChatHistory((prev) => [...prev, aiMessage]);
    } catch (error) {
      console.error('Error with RAG API:', error);
      const errorMessage = { sender: 'ai', text: `An error occurred: ${error.message}` };
      setChatHistory((prev) => [...prev, errorMessage]);
    } finally {
      setIsChatLoading(false);
    }
  };

  // Filter files based on search term
  const filteredFiles = fileSearchTerm
    ? files.filter(file => file.toLowerCase().includes(fileSearchTerm.toLowerCase()))
    : files;
  
  const renderWelcomeView = () => (
    <div className="welcome-container">
      <div className="theme-toggle-container">
        <ThemeToggle />
      </div>
      <div className="logo-title">
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect width="48" height="48" rx="16" fill="url(#paint0_linear)" />
          <path d="M32 16H16C14.9 16 14 16.9 14 18V30C14 31.1 14.9 32 16 32H32C33.1 32 34 31.1 34 30V18C34 16.9 33.1 16 32 16ZM31 21H28V27H26V21H23V19H31V21Z" fill="white"/>
          <path d="M14 23L24 18L34 23" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M24 18V14" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          <defs>
            <linearGradient id="paint0_linear" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
              <stop stopColor="#805AD5" />
              <stop offset="1" stopColor="#553C9A" />
            </linearGradient>
          </defs>
        </svg>
        <h1>Codebase Analyzer</h1>
      </div>
      <p className="subtitle">Understand your code structure, relationships, and implementation details with AI-powered analysis</p>
      <form onSubmit={handleSubmitRepo} className="repo-form">
        <input
          type="text"
          value={githubUrl}
          onChange={(e) => setGithubUrl(e.target.value)}
          placeholder="Enter GitHub repository URL"
        />
        <button type="submit">Analyze</button>
      </form>
      {statusMessage && apiState === API_STATUS.ERROR && <p className="error-message">{statusMessage}</p>}
    </div>
  );

  const renderLoadingView = () => (
    <div className="loading-container">
      <div className="theme-toggle-container">
        <ThemeToggle />
      </div>
      <div className="spinner"></div>
      <h2>{apiState === API_STATUS.FETCHING ? 'Fetching Repository...' : 'Processing Files...'}</h2>
      <p>{statusMessage}</p>
      
      {apiState === API_STATUS.PROCESSING && (
        <div className="progress-container">
          <div className="progress-bar">
            <div 
              className="progress-fill" 
              style={{ width: `${processingProgress.percentage || 0}%` }}
            ></div>
          </div>
          <div className="progress-stats">
            {typeof processingProgress.processed === 'number' ? processingProgress.processed : '?'} / 
            {typeof processingProgress.total === 'number' ? processingProgress.total : '?'} files
          </div>
          {processingProgress.currentFile && (
            <div className="current-file">
              <span>Currently processing:</span> {processingProgress.currentFile}
            </div>
          )}
        </div>
      )}
    </div>
  );

  const renderFileSelectionView = () => (
    <div className="file-selection-container">
      <div className="file-selection-header">
        <h2>Select Files to Analyze</h2>
        <ThemeToggle />
      </div>
      <p>{files.length} files found in the repository. Select the files you want to analyze.</p>
      
      <div className="file-search">
        <input
          type="text"
          placeholder="Search files..."
          value={fileSearchTerm}
          onChange={(e) => setFileSearchTerm(e.target.value)}
        />
        {fileSearchTerm && (
          <button 
            className="clear-search" 
            onClick={() => setFileSearchTerm('')}
            aria-label="Clear search"
          >
            ✕
          </button>
        )}
      </div>
      
      {files.length === 0 && (
        <div className="no-files-message">
          <h3>No files found in repository</h3>
          <p>This could be due to:</p>
          <ul>
            <li>The repository is empty</li>
            <li>Files may be in nested directories not visible</li>
            <li>There was an error retrieving files</li>
          </ul>
          <button onClick={() => setUiState('welcome')} className="back-button">
            Go Back
          </button>
        </div>
      )}
      
      {files.length > 0 && (
        <>
          <div className="file-list-actions">
            <button onClick={handleSelectAll} className="select-all-button">
              {selectedFiles.size === filteredFiles.length && filteredFiles.length > 0 ? 'Deselect All' : 'Select All'}
            </button>
            <span className="file-count">
              {selectedFiles.size} file{selectedFiles.size !== 1 ? 's' : ''} selected
            </span>
          </div>
          
          <div className="file-list">
            {filteredFiles.length > 0 ? (
              filteredFiles.map((file, index) => (
                <div key={index} className="file-item">
                  <input
                    type="checkbox"
                    id={`file-${index}`}
                    checked={selectedFiles.has(file)}
                    onChange={() => handleFileSelect(file)}
                  />
                  <label htmlFor={`file-${index}`}>
                    <span className="file-name">{file}</span>
                  </label>
                </div>
              ))
            ) : (
              <div className="no-results">
                {fileSearchTerm ? 'No matching files found' : 'No files available'}
              </div>
            )}
          </div>
          <div className="file-selection-footer">
            <button 
              onClick={handleProcessSelectedFiles} 
              disabled={selectedFiles.size === 0}
              className="process-button"
            >
              Analyze {selectedFiles.size} Selected File{selectedFiles.size !== 1 ? 's' : ''}
            </button>
          </div>
        </>
      )}
    </div>
  );

  const renderChatView = () => {
    // Function to format code blocks
    const formatMessage = (text) => {
      if (!text) return '';
      
      // Split by code blocks
      const parts = text.split(/```([^`]+)```/);
      if (parts.length === 1) return text; // No code blocks
      
      const result = [];
      for (let i = 0; i < parts.length; i++) {
        if (i % 2 === 0) {
          // Regular text - split by new lines to create proper paragraphs
          if (parts[i].trim()) {
            const paragraphs = parts[i].split('\n').filter(p => p.trim());
            paragraphs.forEach((p, idx) => {
              result.push(<p key={`${i}-${idx}`}>{p}</p>);
            });
          }
        } else {
          // Code block
          result.push(
            <pre key={i}>
              <code>{parts[i]}</code>
            </pre>
          );
        }
      }
      
      return result.length > 0 ? result : text;
    };

    return (
      <div className="chat-container">
        <div className={`chat-header ${isHeaderVisible ? '' : 'hidden'}`}>
          <h2>Code Analysis Assistant</h2>
          <div className="header-actions">
            <button 
              className="start-new-button" 
              onClick={handleStartNewClick}
              disabled={isClearing}
            >
              Start New
            </button>
            <ThemeToggle />
          </div>
        </div>
        
        {/* Confirmation Dialog */}
        {showConfirmDialog && (
          <div className="confirm-dialog-backdrop">
            <div className="confirm-dialog">
              <h3>Start New Analysis?</h3>
              <p>This will clear all current data and return to the GitHub URL input. Are you sure?</p>
              <div className="confirm-dialog-buttons">
                <button 
                  onClick={handleCancelStartNew}
                  disabled={isClearing}
                  className="cancel-button"
                >
                  Cancel
                </button>
                <button 
                  onClick={handleConfirmStartNew}
                  disabled={isClearing}
                  className="confirm-button"
                >
                  {isClearing ? 'Clearing...' : 'Yes, Start New'}
                </button>
              </div>
            </div>
          </div>
        )}
        
        <div className="chat-history">
          {chatHistory.length === 0 ? (
            <div className="empty-chat">
              <div className="empty-chat-icon">
                <svg width="64" height="64" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <rect width="64" height="64" rx="32" fill="url(#paint0_linear)" fillOpacity="0.1"/>
                  <path d="M42.6667 21.3333H21.3334C19.8667 21.3333 18.6667 22.5333 18.6667 24V40C18.6667 41.4667 19.8667 42.6667 21.3334 42.6667H42.6667C44.1334 42.6667 45.3334 41.4667 45.3334 40V24C45.3334 22.5333 44.1334 21.3333 42.6667 21.3333ZM41.3334 28H37.3334V36H34.6667V28H30.6667V25.3333H41.3334V28Z" fill="var(--accent-color)"/>
                  <path d="M18.6667 32L32 25.3333L45.3334 32" stroke="var(--accent-color)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  <defs>
                    <linearGradient id="paint0_linear" x1="0" y1="0" x2="64" y2="64" gradientUnits="userSpaceOnUse">
                      <stop stopColor="var(--accent-color)" />
                      <stop offset="1" stopColor="var(--accent-dark)" />
                    </linearGradient>
                  </defs>
                </svg>
              </div>
              <h3>Start Your Conversation</h3>
              <p>Ask questions about your code's structure, functions, and relationships</p>
            </div>
          ) : (
            chatHistory.map((msg, index) => (
              <div key={index} className={`chat-message ${msg.sender}`}>
                <div className="avatar">
                  <div className={`avatar-icon ${msg.sender}`}></div>
                </div>
                <div className="message-content">
                  {typeof msg.text === 'string' ? formatMessage(msg.text) : msg.text}
                </div>
              </div>
            ))
          )}
          {isChatLoading && (
            <div className="chat-message ai">
              <div className="avatar">
                <div className="avatar-icon ai"></div>
              </div>
              <div className="message-content">
                <p>Thinking<span className="typing-indicator"></span></p>
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>
        <div className="chat-footer">
          <form onSubmit={handleChatQuerySubmit} className="chat-form">
            <input
              type="text"
              value={chatQuery}
              onChange={(e) => setChatQuery(e.target.value)}
              placeholder="Ask about your code structure, functions, relationships..."
              disabled={isChatLoading}
            />
            <button type="submit" disabled={isChatLoading || !chatQuery.trim()}></button>
          </form>
          <div className="footer-text">
            Ask questions about your codebase structure, functions, and relationships
          </div>
        </div>
      </div>
    );
  };

  // Main render logic
  const renderContent = () => {
    switch (uiState) {
      case 'welcome':
        return renderWelcomeView();
      case 'loading':
        return renderLoadingView();
      case 'file-selection':
        return renderFileSelectionView();
      case 'chat':
        return renderChatView();
      default:
        return renderWelcomeView();
    }
  };

  return (
    <div className={`App ${theme}-theme`}>
      {renderContent()}
    </div>
  );
}

export default App;