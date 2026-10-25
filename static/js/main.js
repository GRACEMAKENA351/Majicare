// MajiCare Mobile App - Main JavaScript
// This file handles API communication and app state

const API_BASE_URL = "http://127.0.0.1:5000/api";

class MajiCareAPI {
  constructor() {
    this.token = localStorage.getItem("maji_token");
  }

  async request(endpoint, options = {}) {
    const headers = {
      "Content-Type": "application/json",
      ...options.headers,
    };

    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }

    const response = await fetch(`${API_BASE_URL}/${endpoint}`, {
      ...options,
      headers,
    });

    if (response.status === 401) {
      this.token = null;
      localStorage.removeItem("maji_token");
      window.location.href = "/login";
    }

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "An error occurred");
    }

    return data;
  }

  async register(username, email, password) {
    return this.request("register", {
      method: "POST",
      body: JSON.stringify({ username, email, password }),
    });
  }

  async login(username, password) {
    const data = await this.request("login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    this.token = data.token;
    localStorage.setItem("maji_token", this.token);
    return data;
  }

  async getCommunities(county = "") {
    const params = county ? `?county=${encodeURIComponent(county)}` : "";
    return this.request(`communities${params}`);
  }

  async getWaterPoints() {
    return this.request("water-points");
  }

  async createReport(title, description, communityId) {
    return this.request("reports", {
      method: "POST",
      body: JSON.stringify({ title, description, community_id: communityId }),
    });
  }

  async updateReportStatus(reportId, status) {
    return this.request(`reports/${reportId}/status`, {
      method: "PUT",
      body: JSON.stringify({ status }),
    });
  }

  async getMyProfile() {
    return this.request("me");
  }

  async getCommunityReports(communityId) {
    return this.request(`communities/${communityId}/reports`);
  }

  logout() {
    this.token = null;
    localStorage.removeItem("maji_token");
  }
}

// Initialize the app
document.addEventListener("DOMContentLoaded", () => {
  const api = new MajiCareAPI();

  // Check if user is logged in
  if (localStorage.getItem("maji_token")) {
    // User is logged in, redirect to home
    window.location.href = "/";
  }
});
