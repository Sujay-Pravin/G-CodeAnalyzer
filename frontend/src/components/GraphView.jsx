import React, { useEffect, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';

function GraphView({ graphData, selectedFile, isLoading }) {
  const graphRef = useRef();
  const [hoveredNode, setHoveredNode] = useState(null);
  const [currentZoom, setCurrentZoom] = useState(1);
  const [nodeSize, setNodeSize] = useState(8);
  const [linkStrength, setLinkStrength] = useState(0.6);
  
  // Helper function to get node color
  const getNodeColor = (node) => {
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
      'source_file': '#FF9800'
    };
    
    return typeColors[node.type] || '#CCCCCC';
  };
  
  // Helper function to get link color
  const getLinkColor = (link) => {
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
      'returns': '#00BCD4'
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
    
    window.addEventListener('graph-center', centerGraph);
    window.addEventListener('graph-reset', resetLayout);
    window.addEventListener('graph-node-size', setNodeSizeEvent);
    window.addEventListener('graph-link-strength', setLinkStrengthEvent);
    window.addEventListener('graph-refresh', refreshGraph);
    
    return () => {
      window.removeEventListener('graph-center', centerGraph);
      window.removeEventListener('graph-reset', resetLayout);
      window.removeEventListener('graph-node-size', setNodeSizeEvent);
      window.removeEventListener('graph-link-strength', setLinkStrengthEvent);
      window.removeEventListener('graph-refresh', refreshGraph);
    };
  }, [linkStrength]);

  // Handle zoom events to update current zoom level
  const handleZoom = ({ k }) => {
    setCurrentZoom(k);
  };

  // Node canvas object - show labels at high zoom levels
  const getNodeCanvasObject = (node, ctx, globalScale) => {
    const label = node.label || node.id;
    const fontSize = 12 / globalScale;
    const baseNodeSize = node.type === 'source_file' ? nodeSize * 1.5 : nodeSize;
    const nodeColor = getNodeColor(node);

    // Draw node circle
    ctx.beginPath();
    ctx.arc(node.x, node.y, baseNodeSize, 0, 2 * Math.PI);
    ctx.fillStyle = nodeColor;
    ctx.fill();
    ctx.strokeStyle = 'white';
    ctx.lineWidth = 1.5 / globalScale;
    ctx.stroke();
    
    // Show labels when zoom > 1.5 or when node is hovered
    if (currentZoom > 1.5 || node === hoveredNode) {
      ctx.font = `${fontSize}px Sans-Serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = 'white';
      
      // Add background for better readability
      const textWidth = ctx.measureText(label).width;
      const bckgDimensions = [textWidth, fontSize].map(n => n + fontSize * 0.5);
      
      ctx.fillStyle = 'rgba(0,0,0,0.7)';
      ctx.fillRect(
        node.x - bckgDimensions[0] / 2,
        node.y - bckgDimensions[1] / 2 + baseNodeSize + 4, 
        bckgDimensions[0],
        bckgDimensions[1]
      );
      
      ctx.fillStyle = 'white';
      ctx.fillText(label, node.x, node.y + baseNodeSize + 4);
    }
  };

  return (
    <div className="graph-view">
      <div className="graph-view-header">
        <h3>Graph View</h3>
        {selectedFile && <p className="selected-file-info">{selectedFile.path}</p>}
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
              const baseNodeSize = node.type === 'source_file' ? nodeSize * 1.5 : nodeSize;
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
              }
            }}
            width={800}
            height={600}
          />
        )}
      </div>
    </div>
  );
}

export default GraphView; 