<!-- Dashboard.vue -->
<template>
    <div class="dashboard-container">
      <iframe 
        v-if="!showFallback" 
        :src="primaryDashboardUrl" 
        width="100%" 
        height="600px" 
        frameborder="0"
        @load="handleIframeLoad" 
        @error="handleIframeError"
        ref="dashboardIframe">
      </iframe>
      
      <iframe 
        v-if="showFallback" 
        :src="fallbackDashboardUrl" 
        width="100%" 
        height="600px" 
        frameborder="0">
      </iframe>
      
      <div v-if="loading" class="loading-indicator">
        Loading dashboard...
      </div>
      
      <div v-if="error" class="error-message">
        Could not load dashboard. Please try again later.
      </div>
    </div>
  </template>
  
  <script>
  export default {
    name: 'Dashboard',
    data() {
      return {
        primaryDashboardUrl: 'https://nuracrm-test.onedesk.app/insights/shared/dashboard/e35j7h0e16',
        fallbackDashboardUrl: 'https://nuracrm.onedesk.app/insights/workbook/1/dashboard/r5eee6i04e',
        showFallback: false,
        loading: true,
        error: false,
        loadTimeout: null
      };
    },
    mounted() {
      // Set a timeout to detect loading issues
      this.loadTimeout = setTimeout(() => {
        if (this.loading) {
          this.handleIframeError();
        }
      }, 10000); // 10 seconds timeout
    },
    beforeDestroy() {
      if (this.loadTimeout) {
        clearTimeout(this.loadTimeout);
      }
    },
    methods: {
      handleIframeLoad() {
        this.loading = false;
        clearTimeout(this.loadTimeout);
        
        // Check if the iframe loaded an error page
        try {
          // This might fail due to cross-origin policies
          const iframeContent = this.$refs.dashboardIframe.contentWindow.document.body.innerHTML;
          if (iframeContent.includes('refused to connect') || iframeContent.includes('error')) {
            this.handleIframeError();
          }
        } catch (e) {
          // Cannot access iframe content due to same-origin policy - this is expected
          console.log('Cannot check iframe content due to same-origin policy');
        }
      },
      handleIframeError() {
        console.error('Primary dashboard failed to load, switching to fallback');
        this.loading = false;
        this.error = true;
        
        // Wait a moment before showing fallback
        setTimeout(() => {
          this.showFallback = true;
          this.error = false;
        }, 1000);
      }
    }
  };
  </script>
  
  <style scoped>
  .dashboard-container {
    position: relative;
    width: 100%;
    min-height: 600px;
  }
  
  .loading-indicator {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    text-align: center;
  }
  
  .error-message {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    color: red;
    text-align: center;
  }
  </style>