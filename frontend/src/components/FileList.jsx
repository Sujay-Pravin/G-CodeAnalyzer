import React, { useState } from 'react';

function FileList({ files, selectedFile, onFileSelect, isLoading }) {
  const [searchTerm, setSearchTerm] = useState('');
  const [error, setError] = useState(null);
  const [expandedFolders, setExpandedFolders] = useState({});

  // Filter files based on search term
  const filteredFiles = files?.filter(file => 
    file.path?.toLowerCase().includes(searchTerm.toLowerCase())
  ) || [];
  
  // Group files by folder structure
  const getFolderStructure = (files) => {
    const structure = {};
    
    files.forEach(file => {
      if (!file.path) return;
      
      const parts = file.path.split('/');
      let currentLevel = structure;
      
      // Process all directories in the path
      for (let i = 0; i < parts.length - 1; i++) {
        const part = parts[i];
        if (!currentLevel[part]) {
          currentLevel[part] = {};
        }
        currentLevel = currentLevel[part];
      }
      
      // Add the file to the last level
      const fileName = parts[parts.length - 1];
      currentLevel[fileName] = file;
    });
    
    return structure;
  };
  
  // Calculate folder structure
  const folderStructure = getFolderStructure(filteredFiles);
  
  // Count files in a folder
  const countFilesInFolder = (obj) => {
    let count = 0;
    for (const key in obj) {
      if (typeof obj[key] === 'object' && !obj[key].path) {
        // It's a folder
        count += countFilesInFolder(obj[key]);
      } else {
        // It's a file
        count++;
      }
    }
    return count;
  };

  // Toggle folder expanded state
  const toggleFolder = (folderPath) => {
    setExpandedFolders(prev => ({
      ...prev,
      [folderPath]: !prev[folderPath]
    }));
  };
  
  // Handle repo context selection
  const handleRepoContextSelect = () => {
    // Create a virtual "file" object for repo context
    const repoContextObj = {
      path: "__repo_context__",
      name: "Entire Repository",
      isRepoContext: true
    };
    
    onFileSelect(repoContextObj);
  };
  
  // Render folder structure recursively
  const renderFolderStructure = (structure, path = '', level = 0) => {
    const entries = Object.entries(structure);
    
    return entries.map(([key, value]) => {
      const currentPath = path ? `${path}/${key}` : key;
      const isFile = value && value.path;
      
      if (isFile) {
        // Render file entry
        return (
          <div
            key={value.path}
            className={`file-item ${selectedFile && selectedFile.path === value.path ? 'selected' : ''}`}
            onClick={() => onFileSelect(value)}
            style={{ paddingLeft: `${(level + 1) * 20}px` }}
          >
            <div className="file-item-inner">
              <svg className="file-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M14 2H6C5.46957 2 4.96086 2.21071 4.58579 2.58579C4.21071 2.96086 4 3.46957 4 4V20C4 20.5304 4.21071 21.0391 4.58579 21.4142C4.96086 21.7893 5.46957 22 6 22H18C18.5304 22 19.0391 21.7893 19.4142 21.4142C19.7893 21.0391 20 20.5304 20 20V8L14 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M14 2V8H20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              <span className="file-name">{key}</span>
            </div>
          </div>
        );
      } else {
        // It's a folder - render expandable folder with children
        const isExpanded = expandedFolders[currentPath] !== false; // Default to expanded
        const fileCount = countFilesInFolder(value);
        
        return (
          <div key={currentPath} className="folder-item">
            <div 
              className="folder-header" 
              style={{ paddingLeft: `${level * 20}px` }}
              onClick={() => toggleFolder(currentPath)}
            >
              <svg
                className={`folder-toggle ${isExpanded ? 'expanded' : ''}`}
                width="16"
                height="16"
                viewBox="0 0 16 16"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path
                  d="M6 12L10 8L6 4"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <svg className="folder-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M22 19C22 19.5304 21.7893 20.0391 21.4142 20.4142C21.0391 20.7893 20.5304 21 20 21H4C3.46957 21 2.96086 20.7893 2.58579 20.4142C2.21071 20.0391 2 19.5304 2 19V5C2 4.46957 2.21071 3.96086 2.58579 3.58579C2.96086 3.21071 3.46957 3 4 3H9L11 6H20C20.5304 6 21.0391 6.21071 21.4142 6.58579C21.7893 6.96086 22 7.46957 22 8V19Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              <span className="folder-name">{key}</span>
              <span className="folder-count">{fileCount}</span>
            </div>
            
            {isExpanded && (
              <div className="nested-folder">
                {renderFolderStructure(value, currentPath, level + 1)}
              </div>
            )}
          </div>
        );
      }
    });
  };

  const renderFilesList = () => {
    if (isLoading) {
      return (
        <div className="loading-container">
          <div className="spinner">
            <div className="bounce1"></div>
            <div className="bounce2"></div>
            <div className="bounce3"></div>
          </div>
          <p>Loading files...</p>
        </div>
      );
    }
    
    if (error) {
      return (
        <div className="error-message">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 9V11M12 15H12.01M5.07183 19H18.9282C20.4678 19 21.4301 17.3333 20.6603 16L13.7321 4C12.9623 2.66667 11.0378 2.66667 10.268 4L3.33978 16C2.56998 17.3333 3.53223 19 5.07183 19Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          <p>{error}</p>
          <button className="retry-button" onClick={() => window.location.reload()}>
            Retry
          </button>
        </div>
      );
    }

    if (!files || files.length === 0) {
      return (
        <div className="no-files-message">
          <p>No files available</p>
        </div>
      );
    }
    
    if (filteredFiles.length === 0) {
      return (
        <div className="no-files-message">
          <p>No files match your search</p>
        </div>
      );
    }
    
    return (
      <div className="file-tree">
        {/* Repo Context Option */}
        <div 
          className={`repo-context-item ${selectedFile && selectedFile.isRepoContext ? 'selected' : ''}`}
          onClick={handleRepoContextSelect}
        >
          <div className="file-item-inner">
            <svg className="repo-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M2 17L12 22L22 17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M2 12L12 17L22 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            <span className="repo-name">Repo Context</span>
          </div>
        </div>
        
        {renderFolderStructure(folderStructure)}
      </div>
    );
  };

  return (
    <div className="file-list-container">
      <div className="file-list-header">
        <h3>Files</h3>
        <div className="file-search">
          <input
            type="text"
            placeholder="Search files..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            disabled={isLoading}
          />
          {searchTerm && (
            <button 
              className="search-clear-btn" 
              onClick={() => setSearchTerm('')}
              aria-label="Clear search"
              disabled={isLoading}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          )}
        </div>
      </div>
      
      <div className="file-list-content">
        {renderFilesList()}
      </div>
    </div>
  );
}

export default FileList; 