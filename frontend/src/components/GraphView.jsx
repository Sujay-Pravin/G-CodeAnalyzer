import React, { useEffect, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';

function GraphView({ graphData, selectedFile, isLoading }) {
  const graphRef = useRef();
  const [hoveredNode, setHoveredNode] = useState(null);
  const [currentZoom, setCurrentZoom] = useState(1);
  const [nodeSize, setNodeSize] = useState(8);
  const [linkStrength, setLinkStrength] = useState(0.6);
  const [highlightedNodes, setHighlightedNodes] = useState(new Set());
  
  // Helper function to get node color
  const getNodeColor = (node) => {
    // If the node is highlighted, use a brighter color
    if (highlightedNodes.has(node.id) || highlightedNodes.has(node.name)) {
      return '#FFD700'; // Gold color for highlighted nodes
    }
    
    const typeColors = {
      'Function': '#4285F4',
      'Variable': '#34A853',
      'Class': '#EA4335',
      'Module': '#FBBC05',
      'Method': '#9C27B0',
      'Interface': '#3F51B5',
      'Property': '#009688',
      'Type': '#FF5722',
      'Enum': '#795548',
      'Namespace': '#607D8B',
      'Parameter': '#8BC34A',
      'Operation': '#00BCD4',
      'source_file': '#FF9800',
      'File': '#FF9800',
      'Repository': '#3cb4ff'
    };
    
    return typeColors[node.type] || '#CCCCCC';
  };
  
  // Helper function to get link color
  const getLinkColor = (link) => {
    // If both source and target are highlighted, highlight the link
    const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
    const targetId = typeof link.target === 'object' ? link.target.id : link.target;
    const sourceName = typeof link.source === 'object' ? link.source.name : null;
    const targetName = typeof link.target === 'object' ? link.target.name : null;
    
    if ((highlightedNodes.has(sourceId) || (sourceName && highlightedNodes.has(sourceName))) && 
        (highlightedNodes.has(targetId) || (targetName && highlightedNodes.has(targetName)))) {
      return '#FFD700'; // Gold color for highlighted links
    }
    
    const relationshipColors = {
      'calls': '#4285F4',
      'defines': '#34A853',
      'uses': '#EA4335',
      'imports': '#FBBC05',
      'inherits': '#9C27B0',
      'implements': '#3F51B5',
      'contains': '#009688',
      'depends_on': '#FF5722',
      'extends': '#795548',
      'references': '#607D8B',
      'contains_operation': '#8BC34A',
      'returns': '#00BCD4',
      'CALLS': '#4285F4',
      'DEFINES': '#34A853',
      'USES': '#EA4335',
      'IMPORTS': '#FBBC05',
      'CONTAINS': '#009688',
      'DEPENDS_ON': '#FF5722'
    };
    
    return relationshipColors[link.type] || '#AAAAAA';
  };
  
  // Reset and initialize the graph when data changes
  useEffect(() => {
    if (graphRef.current && graphData && graphData.nodes && graphData.nodes.length > 0) {
      // Reset forces
      graphRef.current.d3Force('charge').strength(-150);
      graphRef.current.d3Force('link').distance(70);
      graphRef.current.d3Force('link').strength(linkStrength);
      
      // Reheat the simulation to recalculate positions
      graphRef.current.d3ReheatSimulation();
      
      // Reset highlights when graph data changes
      setHighlightedNodes(new Set());
    }
  }, [graphData, linkStrength]);
  
  // Set up event handlers
  useEffect(() => {
    if (!graphRef.current) return;
    
    // Set up event handlers for the zoom buttons
    const centerGraph = () => {
      if (graphRef.current) {
        graphRef.current.centerAt();
        graphRef.current.zoom(1);
        setCurrentZoom(1);
      }
    };
    
    const resetLayout = () => {
      if (graphRef.current) {
        graphRef.current.d3ReheatSimulation();
      }
    };
    
    const setNodeSizeEvent = (e) => {
      const size = parseFloat(e.detail.size);
      setNodeSize(size);
      if (graphRef.current) {
        graphRef.current.refresh();
      }
    };
    
    const setLinkStrengthEvent = (e) => {
      const strength = parseFloat(e.detail.strength);
      setLinkStrength(strength);
      if (graphRef.current) {
        graphRef.current.d3Force('link').strength(strength);
        graphRef.current.d3ReheatSimulation();
      }
    };
    
    const refreshGraph = () => {
      if (graphRef.current) {
        // Force a complete re-initialization of the simulation
        graphRef.current.d3Force('charge').strength(-150);
        graphRef.current.d3Force('link').distance(70);
        graphRef.current.d3Force('link').strength(linkStrength);
        
        // Completely reheat the simulation
        graphRef.current.d3ReheatSimulation();
        graphRef.current.refresh();
      }
    };
    
    // Handle highlighting nodes based on chat context
    const highlightNodes = (e) => {
      if (!e.detail || !e.detail.nodeNames || !graphData || !graphData.nodes) return;
      
      const nodeNames = e.detail.nodeNames;
      const newHighlightedNodes = new Set(nodeNames);
      
      // Find matching nodes by name or id
      graphData.nodes.forEach(node => {
        if (nodeNames.includes(node.name) || nodeNames.includes(node.id) || 
            (node.label && nodeNames.includes(node.label))) {
          newHighlightedNodes.add(node.id);
          newHighlightedNodes.add(node.name);
          
          // If a node is highlighted, center the graph on it
          if (graphRef.current) {
            graphRef.current.centerAt(node.x, node.y, 1000);
            graphRef.current.zoom(1.5, 1000);
            setCurrentZoom(1.5);
            
            // Only center on the first matching node
            return;
          }
        }
      });
      
      setHighlightedNodes(newHighlightedNodes);
      
      if (graphRef.current) {
        graphRef.current.refresh();
      }
    };
    
    window.addEventListener('graph-center', centerGraph);
    window.addEventListener('graph-reset', resetLayout);
    window.addEventListener('graph-node-size', setNodeSizeEvent);
    window.addEventListener('graph-link-strength', setLinkStrengthEvent);
    window.addEventListener('graph-refresh', refreshGraph);
    window.addEventListener('highlight-nodes', highlightNodes);
    
    return () => {
      window.removeEventListener('graph-center', centerGraph);
      window.removeEventListener('graph-reset', resetLayout);
      window.removeEventListener('graph-node-size', setNodeSizeEvent);
      window.removeEventListener('graph-link-strength', setLinkStrengthEvent);
      window.removeEventListener('graph-refresh', refreshGraph);
      window.removeEventListener('highlight-nodes', highlightNodes);
    };
  }, [linkStrength, graphData]);

  // Handle zoom events to update current zoom level
  const handleZoom = ({ k }) => {
    setCurrentZoom(k);
  };

  // Clear highlighted nodes on click outside
  const handleBackgroundClick = () => {
    if (highlightedNodes.size > 0) {
      setHighlightedNodes(new Set());
      if (graphRef.current) {
        graphRef.current.refresh();
      }
    }
  };

  // Node canvas object - show labels at high zoom levels
  const getNodeCanvasObject = (node, ctx, globalScale) => {
    const label = node.label || node.id;
    const fontSize = 12 / globalScale;
    const baseNodeSize = node.type === 'source_file' || node.type === 'File' ? nodeSize * 1.5 : nodeSize;
    const isHighlighted = highlightedNodes.has(node.id) || highlightedNodes.has(node.name);
    const nodeColor = getNodeColor(node);

    // Draw node circle
    ctx.beginPath();
    ctx.arc(node.x, node.y, baseNodeSize + (isHighlighted ? 2 : 0), 0, 2 * Math.PI);
    ctx.fillStyle = nodeColor;
    ctx.fill();
    
    // Add a highlight outline for highlighted nodes
    if (isHighlighted) {
      ctx.strokeStyle = '#FFD700';
      ctx.lineWidth = 2.5 / globalScale;
      ctx.stroke();
    } else {
      ctx.strokeStyle = 'white';
      ctx.lineWidth = 1.5 / globalScale;
      ctx.stroke();
    }
    
    // Show labels when zoom > 1.5 or when node is hovered or highlighted
    if (currentZoom > 1.5 || node === hoveredNode || isHighlighted) {
      ctx.font = `${fontSize}px Sans-Serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = 'white';
      
      // Add background for better readability
      const textWidth = ctx.measureText(label).width;
      const bckgDimensions = [textWidth, fontSize].map(n => n + fontSize * 0.5);
      
      ctx.fillStyle = isHighlighted ? 'rgba(255, 215, 0, 0.5)' : 'rgba(0,0,0,0.7)';
      ctx.fillRect(
        node.x - bckgDimensions[0] / 2,
        node.y - bckgDimensions[1] / 2 + baseNodeSize + 4, 
        bckgDimensions[0],
        bckgDimensions[1]
      );
      
      ctx.fillStyle = isHighlighted ? 'black' : 'white';
      ctx.fillText(label, node.x, node.y + baseNodeSize + 4);
    }
  };

  return (
    <div className="graph-view">
      <div className="graph-view-header">
        <h3>Graph View</h3>
        {selectedFile && <p className="selected-file-info">{selectedFile.path}</p>}
        {highlightedNodes.size > 0 && (
          <button 
            className="clear-highlights-btn"
            onClick={() => setHighlightedNodes(new Set())}
          >
            Clear Highlights
          </button>
        )}
      </div>
      
      <div className="graph-container">
        {isLoading ? (
          <div className="loading-container">
            <div className="spinner">
              <div className="bounce1"></div>
              <div className="bounce2"></div>
              <div className="bounce3"></div>
            </div>
            <p>Building graph visualization...</p>
          </div>
        ) : !graphData || !graphData.nodes || graphData.nodes.length === 0 ? (
          <div className="no-graph-data">
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M17 11H13V7M21 21L17 17M17 3C17 4.10457 16.1046 5 15 5C13.8954 5 13 4.10457 13 3C13 1.89543 13.8954 1 15 1C16.1046 1 17 1.89543 17 3ZM11 15C11 16.1046 10.1046 17 9 17C7.89543 17 7 16.1046 7 15C7 13.8954 7.89543 13 9 13C10.1046 13 11 13.8954 11 15ZM19 9C19 10.1046 18.1046 11 17 11C15.8954 11 15 10.1046 15 9C15 7.89543 15.8954 7 17 7C18.1046 7 19 7.89543 19 9ZM7 7C7 8.10457 6.10457 9 5 9C3.89543 9 3 8.10457 3 7C3 5.89543 3.89543 5 5 5C6.10457 5 7 5.89543 7 7Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            <p>{selectedFile ? 'No graph data available for this file' : 'Select a file to view graph'}</p>
          </div>
        ) : (
          <ForceGraph2D
            ref={graphRef}
            graphData={graphData}
            nodeId="id"
            nodeLabel={(node) => `${node.label || node.id} (${node.type})`}
            nodeCanvasObject={getNodeCanvasObject}
            nodePointerAreaPaint={(node, color, ctx) => {
              const baseNodeSize = node.type === 'source_file' || node.type === 'File' ? nodeSize * 1.5 : nodeSize;
              ctx.beginPath();
              ctx.arc(node.x, node.y, baseNodeSize + 2, 0, 2 * Math.PI);
              ctx.fillStyle = color;
              ctx.fill();
            }}
            linkColor={getLinkColor}
            linkDirectionalArrowLength={3.5}
            linkDirectionalArrowRelPos={1}
            linkCurvature={0.25}
            linkDirectionalParticles={3}
            linkDirectionalParticleSpeed={0.01}
            cooldownTicks={100}
            onNodeHover={node => setHoveredNode(node)}
            onZoom={handleZoom}
            onNodeClick={(node) => {
              // Handle node click (e.g., focus on node)
              if (graphRef.current) {
                graphRef.current.centerAt(node.x, node.y, 1000);
                graphRef.current.zoom(1.5, 1000);
                setCurrentZoom(1.5);
                
                // Toggle highlight for this node
                setHighlightedNodes(prev => {
                  const newSet = new Set(prev);
                  if (newSet.has(node.id) || newSet.has(node.name)) {
                    newSet.delete(node.id);
                    newSet.delete(node.name);
                  } else {
                    newSet.add(node.id);
                    if (node.name) newSet.add(node.name);
                  }
                  return newSet;
                });
              }
            }}
            onBackgroundClick={handleBackgroundClick}
            width={800}
            height={600}
          />
        )}
      </div>
    </div>
  );
}

export default GraphView; 