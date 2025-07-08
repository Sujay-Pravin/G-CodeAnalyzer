import React, { useEffect } from 'react';

function GraphControls({ filters, onFilterChange }) {
  const { 
    nodeTypes, 
    relationshipTypes, 
    showAllNodeTypes, 
    showAllRelationshipTypes,
    enabledNodeTypes = new Set(),
    enabledRelationshipTypes = new Set()
  } = filters;

  // Trigger graph refresh when filters change
  useEffect(() => {
    const timer = setTimeout(() => {
      window.dispatchEvent(new CustomEvent('graph-refresh'));
    }, 100);
    
    return () => clearTimeout(timer);
  }, [enabledNodeTypes, enabledRelationshipTypes]);

  const handleNodeTypeToggle = (type) => {
    onFilterChange('nodeType', type, !enabledNodeTypes.has(type));
  };

  const handleRelationshipTypeToggle = (type) => {
    onFilterChange('relationshipType', type, !enabledRelationshipTypes.has(type));
  };

  const handleToggleAllNodeTypes = () => {
    onFilterChange('toggleAllNodeTypes', null, !showAllNodeTypes);
  };

  const handleToggleAllRelationshipTypes = () => {
    onFilterChange('toggleAllRelationshipTypes', null, !showAllRelationshipTypes);
  };

  const handleRefreshGraph = () => {
    window.dispatchEvent(new CustomEvent('graph-refresh'));
  };

  return (
    <div className="graph-controls">
      <div className="graph-controls-header">
        <h3>Graph Controls</h3>
      </div>
      
      <div className="graph-controls-content">
        <div className="control-section">
          <div className="control-section-header">
            <h4>Node Types</h4>
            <label className="toggle-all">
              <input
                type="checkbox"
                checked={showAllNodeTypes}
                onChange={handleToggleAllNodeTypes}
              />
              <span className="toggle-switch"></span>
              <span className="toggle-label">All</span>
            </label>
          </div>
          
          <div className="control-options">
            {nodeTypes.length === 0 ? (
              <p className="no-options">No node types available</p>
            ) : (
              <ul className="filter-list">
                {nodeTypes.map((type) => (
                  <li key={type} className="filter-item">
                    <label className="filter-label">
                      <input
                        type="checkbox"
                        checked={enabledNodeTypes.has(type)}
                        onChange={() => handleNodeTypeToggle(type)}
                      />
                      <span className="checkbox-custom"></span>
                      <span className="node-type-indicator" style={{ backgroundColor: getNodeColor(type) }}></span>
                      <span>{type}</span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="control-section">
          <div className="control-section-header">
            <h4>Relationship Types</h4>
            <label className="toggle-all">
              <input
                type="checkbox"
                checked={showAllRelationshipTypes}
                onChange={handleToggleAllRelationshipTypes}
              />
              <span className="toggle-switch"></span>
              <span className="toggle-label">All</span>
            </label>
          </div>
          
          <div className="control-options">
            {relationshipTypes.length === 0 ? (
              <p className="no-options">No relationship types available</p>
            ) : (
              <ul className="filter-list">
                {relationshipTypes.map((type) => (
                  <li key={type} className="filter-item">
                    <label className="filter-label">
                      <input
                        type="checkbox"
                        checked={enabledRelationshipTypes.has(type)}
                        onChange={() => handleRelationshipTypeToggle(type)}
                      />
                      <span className="checkbox-custom"></span>
                      <span className="relationship-type-indicator" style={{ backgroundColor: getRelationshipColor(type) }}></span>
                      <span>{type}</span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="control-section">
          <div className="control-section-header">
            <h4>Layout Options</h4>
          </div>
          
          <div className="control-options">
            <div className="button-group">
              <button className="layout-button primary" onClick={() => window.dispatchEvent(new CustomEvent('graph-center'))}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M21 21L16.65 16.65M11 8V14M8 11H14M19 11C19 15.4183 15.4183 19 11 19C6.58172 19 3 15.4183 3 11C3 6.58172 6.58172 3 11 3C15.4183 3 19 6.58172 19 11Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                Center Graph
              </button>
              
              <button className="layout-button secondary" onClick={() => window.dispatchEvent(new CustomEvent('graph-reset'))}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M4 12V20M4 12H2M4 12H6M4 4V8M4 20H8M4 20H2M12 20H16M20 20H16M20 12V20M20 12H22M20 12H18M20 4V8M12 4H16M8 4H2M16 4H22" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                Reset Layout
              </button>
            </div>
            
            <button className="layout-button refresh" onClick={handleRefreshGraph}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M4 4V9H9M20 20V15H15M20 9C20 13.4183 16.4183 17 12 17C7.58172 17 4 13.4183 4 9C4 4.58172 7.58172 1 12 1C16.4183 1 20 4.58172 20 9Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              Refresh Graph
            </button>
            
            <div className="layout-option">
              <label>Node Size</label>
              <div className="slider-container">
                <span className="slider-icon small">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="12" cy="12" r="6" stroke="currentColor" strokeWidth="2" />
                  </svg>
                </span>
                <input 
                  type="range" 
                  min="4" 
                  max="15" 
                  defaultValue="8"
                  className="styled-slider"
                  onChange={(e) => window.dispatchEvent(new CustomEvent('graph-node-size', { detail: { size: e.target.value } }))}
                />
                <span className="slider-icon large">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" />
                  </svg>
                </span>
              </div>
            </div>
            
            <div className="layout-option">
              <label>Link Strength</label>
              <div className="slider-container">
                <span className="slider-icon weak">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M8 12h8" stroke="currentColor" strokeWidth="2" strokeDasharray="2 2" />
                  </svg>
                </span>
                <input 
                  type="range" 
                  min="0.1" 
                  max="2" 
                  step="0.1" 
                  defaultValue="0.6"
                  className="styled-slider"
                  onChange={(e) => window.dispatchEvent(new CustomEvent('graph-link-strength', { detail: { strength: e.target.value } }))}
                />
                <span className="slider-icon strong">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M8 12h8" stroke="currentColor" strokeWidth="3" />
                  </svg>
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Helper functions for node and relationship colors
const getNodeColor = (type) => {
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
  
  return typeColors[type] || '#CCCCCC';
};

const getRelationshipColor = (type) => {
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
  
  return relationshipColors[type] || '#AAAAAA';
};

export default GraphControls; 