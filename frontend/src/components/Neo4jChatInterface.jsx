import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import FileList from './FileList';
import ChatPanel from './ChatPanel';
import GraphControls from './GraphControls';
import GraphView from './GraphView';
import './Neo4jChatInterface.css';

const RAG_API_URL = 'http://localhost:5001/api/chat';
const BASE_API_URL = 'http://localhost:5001';

function Neo4jChatInterface({ repoId }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [files, setFiles] = useState([]);
  const [fileData, setFileData] = useState(null);
  const [chatHistory, setChatHistory] = useState([]);
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [isFilesLoading, setIsFilesLoading] = useState(false);
  const [isGraphLoading, setIsGraphLoading] = useState(false);
  const [isFileDataLoading, setIsFileDataLoading] = useState(false);
  const [chatQuery, setChatQuery] = useState('');
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [graphFilters, setGraphFilters] = useState({
    nodeTypes: [],
    relationshipTypes: [],
    showAllNodeTypes: true,
    showAllRelationshipTypes: true,
  });
  
  // Fetch files when component mounts
  useEffect(() => {
    if (repoId) {
      fetchFiles();
    }

    // Also set up a listener for CORS/network errors
    const handleError = (event) => {
      if (event.message && event.message.includes("NetworkError")) {
        console.error("Network error detected:", event);
      }
    };
    
    window.addEventListener('error', handleError);
    return () => window.removeEventListener('error', handleError);
  }, [repoId]);

  // Fetch file list with fallback URLs
  const fetchFiles = async () => {
    setIsFilesLoading(true);
    try {
      // Try the first URL format
      let response;
      try {
        response = await axios.get(`${BASE_API_URL}/api/graph/files?repo_id=${repoId}`);
        if (response.data.success) {
          setFiles(response.data.files);
          return;
        }
      } catch (error) {
        console.log("First URL format failed, trying alternative...");
      }

      // Try the second URL format if first fails
      try {
        response = await axios.get(`${BASE_API_URL}/graph/files?repo_id=${repoId}`);
        if (response.data.success) {
          setFiles(response.data.files);
          return;
        }
      } catch (error) {
        console.error('Error fetching files with second URL format:', error);
      }
    } catch (error) {
      console.error('Error fetching files:', error);
    } finally {
      setIsFilesLoading(false);
    }
  };

  // Handle file selection with fallback URLs
  const handleFileSelect = async (file) => {
    setSelectedFile(file);
    // Don't clear chat history when changing files
    // setChatHistory([]);
    setIsFileDataLoading(true);
    setIsGraphLoading(true);
    
    try {
      // Try first URL format for file data
      let response, graphResponse;
      
      try {
        response = await axios.get(`${BASE_API_URL}/api/graph/file-data?repo_id=${repoId}&file_path=${file.path}`);
        if (response.data.success) {
          setFileData(response.data.fileData);
        }
      } catch (error) {
        console.log("First file-data URL format failed, trying alternative...");
        try {
          response = await axios.get(`${BASE_API_URL}/graph/file-data?repo_id=${repoId}&file_path=${file.path}`);
          if (response.data.success) {
            setFileData(response.data.fileData);
          }
        } catch (innerError) {
          console.error('Error fetching file data with alternative URL:', innerError);
        }
      } finally {
        setIsFileDataLoading(false);
      }
      
      // Try first URL format for graph data
      try {
        graphResponse = await axios.get(`${BASE_API_URL}/api/graph/file-graph?repo_id=${repoId}&file_path=${file.path}`);
        if (graphResponse.data.success) {
          // Filter out isolated nodes (nodes without any connections)
          const connectedNodeIds = new Set();
          if (graphResponse.data.graphData.links) {
            graphResponse.data.graphData.links.forEach(link => {
              connectedNodeIds.add(link.source);
              connectedNodeIds.add(link.target);
            });
          }
          
          const filteredNodes = graphResponse.data.graphData.nodes
            ? graphResponse.data.graphData.nodes.filter(node => connectedNodeIds.has(node.id))
            : [];
            
          const filteredGraphData = {
            nodes: filteredNodes,
            links: graphResponse.data.graphData.links || []
          };
          
          setGraphData(filteredGraphData);
          processGraphData(filteredGraphData);
        }
      } catch (error) {
        console.log("First file-graph URL format failed, trying alternative...");
        try {
          graphResponse = await axios.get(`${BASE_API_URL}/graph/file-graph?repo_id=${repoId}&file_path=${file.path}`);
          if (graphResponse.data.success) {
            // Filter out isolated nodes (nodes without any connections)
            const connectedNodeIds = new Set();
            if (graphResponse.data.graphData.links) {
              graphResponse.data.graphData.links.forEach(link => {
                connectedNodeIds.add(link.source);
                connectedNodeIds.add(link.target);
              });
            }
            
            const filteredNodes = graphResponse.data.graphData.nodes
              ? graphResponse.data.graphData.nodes.filter(node => connectedNodeIds.has(node.id))
              : [];
              
            const filteredGraphData = {
              nodes: filteredNodes,
              links: graphResponse.data.graphData.links || []
            };
            
            setGraphData(filteredGraphData);
            processGraphData(filteredGraphData);
          }
        } catch (innerError) {
          console.error('Error fetching graph data with alternative URL:', innerError);
        }
      } finally {
        setIsGraphLoading(false);
      }
    } catch (error) {
      console.error('Error handling file selection:', error);
      setIsFileDataLoading(false);
      setIsGraphLoading(false);
    }
  };

  // Process graph data to extract filters
  const processGraphData = (data) => {
    if (data && data.nodes && data.links) {
      const nodeTypes = [...new Set(data.nodes.map(node => node.type))];
      const relationshipTypes = [...new Set(data.links.map(link => link.type))];
      
      setGraphFilters({
        nodeTypes,
        relationshipTypes,
        showAllNodeTypes: true,
        showAllRelationshipTypes: true,
        enabledNodeTypes: new Set(nodeTypes),
        enabledRelationshipTypes: new Set(relationshipTypes)
      });
    }
  };

  // Handle chat query submission
  const handleChatQuerySubmit = async (e) => {
    e.preventDefault();
    if (!chatQuery.trim() || !selectedFile) return;
    
    const userMessage = { sender: 'user', text: chatQuery };
    setChatHistory(prev => [...prev, userMessage]);
    setIsChatLoading(true);
    setChatQuery('');
    
    try {
      const response = await axios.post(RAG_API_URL, {
        query: chatQuery,
        repo_id: repoId,
        file_path: selectedFile.path,
        context: JSON.stringify(fileData),
      });
      
      if (response.data.success) {
        const aiMessage = { sender: 'ai', text: response.data.response };
        setChatHistory(prev => [...prev, aiMessage]);
      } else {
        const errorMessage = { 
          sender: 'ai', 
          text: 'Sorry, I encountered an error processing your request. Please try again.' 
        };
        setChatHistory(prev => [...prev, errorMessage]);
      }
    } catch (error) {
      console.error('Error sending chat query:', error);
      const errorMessage = { 
        sender: 'ai', 
        text: `Error: ${error.message}. Please try again.` 
      };
      setChatHistory(prev => [...prev, errorMessage]);
    } finally {
      setIsChatLoading(false);
    }
  };

  // Handle graph filter changes
  const handleGraphFilterChange = (filterType, filterValue, isEnabled) => {
    setGraphFilters(prevFilters => {
      const newFilters = { ...prevFilters };
      
      if (filterType === 'nodeType') {
        const newEnabledNodeTypes = new Set(newFilters.enabledNodeTypes);
        
        if (isEnabled) {
          newEnabledNodeTypes.add(filterValue);
        } else {
          newEnabledNodeTypes.delete(filterValue);
        }
        
        newFilters.enabledNodeTypes = newEnabledNodeTypes;
        newFilters.showAllNodeTypes = newEnabledNodeTypes.size === newFilters.nodeTypes.length;
      } 
      else if (filterType === 'relationshipType') {
        const newEnabledRelationshipTypes = new Set(newFilters.enabledRelationshipTypes);
        
        if (isEnabled) {
          newEnabledRelationshipTypes.add(filterValue);
        } else {
          newEnabledRelationshipTypes.delete(filterValue);
        }
        
        newFilters.enabledRelationshipTypes = newEnabledRelationshipTypes;
        newFilters.showAllRelationshipTypes = newEnabledRelationshipTypes.size === newFilters.relationshipTypes.length;
      }
      else if (filterType === 'toggleAllNodeTypes') {
        newFilters.showAllNodeTypes = isEnabled;
        newFilters.enabledNodeTypes = isEnabled 
          ? new Set(newFilters.nodeTypes) 
          : new Set();
      }
      else if (filterType === 'toggleAllRelationshipTypes') {
        newFilters.showAllRelationshipTypes = isEnabled;
        newFilters.enabledRelationshipTypes = isEnabled 
          ? new Set(newFilters.relationshipTypes) 
          : new Set();
      }
      
      return newFilters;
    });
  };

  // Filter graph data based on current filters
  const filteredGraphData = React.useMemo(() => {
    if (!graphFilters.enabledNodeTypes || !graphFilters.enabledRelationshipTypes) {
      return graphData;
    }
    
    const filteredNodes = graphData.nodes.filter(node => 
      graphFilters.enabledNodeTypes.has(node.type)
    );
    
    const filteredNodeIds = new Set(filteredNodes.map(node => node.id));
    
    const filteredLinks = graphData.links.filter(link => 
      graphFilters.enabledRelationshipTypes.has(link.type) &&
      filteredNodeIds.has(link.source.id || link.source) &&
      filteredNodeIds.has(link.target.id || link.target)
    );
    
    // Create a new object to ensure React detects the change
    return {
      nodes: [...filteredNodes],
      links: [...filteredLinks].map(link => {
        // Ensure links have proper references to node objects, not just IDs
        // This is crucial for the force graph to work properly
        if (typeof link.source === 'string' || typeof link.source === 'number') {
          const sourceNode = filteredNodes.find(node => node.id === link.source);
          const targetNode = filteredNodes.find(node => node.id === link.target);
          if (sourceNode && targetNode) {
            return {
              ...link,
              source: sourceNode,
              target: targetNode
            };
          }
        }
        return link;
      })
    };
  }, [graphData, graphFilters]);

  return (
    <div className="neo4j-chat-interface">
      <div className="file-list-column">
        <FileList 
          files={files} 
          selectedFile={selectedFile}
          onFileSelect={handleFileSelect}
          isLoading={isFilesLoading}
        />
      </div>
      
      <div className="chat-panel-column">
        <ChatPanel
          chatHistory={chatHistory}
          chatQuery={chatQuery}
          setChatQuery={setChatQuery}
          handleChatQuerySubmit={handleChatQuerySubmit}
          isChatLoading={isChatLoading}
          selectedFile={selectedFile}
          isFileDataLoading={isFileDataLoading}
        />
      </div>
      
      <div className="graph-controls-column">
        <GraphControls
          filters={graphFilters}
          onFilterChange={handleGraphFilterChange}
        />
      </div>
      
      <div className="graph-view-column">
        <GraphView 
          graphData={filteredGraphData}
          selectedFile={selectedFile}
          isLoading={isGraphLoading}
        />
      </div>
    </div>
  );
}

export default Neo4jChatInterface; 