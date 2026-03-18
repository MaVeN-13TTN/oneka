'use client';

import React, { useEffect, useState } from 'react';
import { useTheme } from 'next-themes';
import { Moon, Sun, Menu, X } from 'lucide-react';
import Globe from '@/components/ui/globe';

export default function LandingPage() {
  const [mounted, setMounted] = useState(false);
  const { theme, setTheme } = useTheme();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
    const getCurrentYear = () => new Date().getFullYear();

  useEffect(() => {
    setMounted(true);
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry, i) => {
        if (entry.isIntersecting) {
          setTimeout(() => entry.target.classList.add('visible'), i * 80);
        }
      });
    }, { threshold: 0.12 });

    document.querySelectorAll('.fade-in').forEach(el => observer.observe(el));
    return () => observer.disconnect();
  }, []);

  return (
    <main>


    {/* NAV */}
    <nav>
        <div className="logo">ONEKA</div>
        
        <button 
            id="mobile-menu-btn" 
            className={`mobile-menu-btn ${mobileMenuOpen ? 'active' : ''}`}
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
        >
            <span />
            <span />
            <span />
        </button>

        <ul className={`nav-links ${mobileMenuOpen ? 'active' : ''}`}>
            <li><a href="#problem">The Problem</a></li>
            <li><a href="#how">How It Works</a></li>
            <li><a href="#features">Platform</a></li>
            <li><a href="#impact">Impact</a></li>
        </ul>
        <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
            
            <button 
                id="theme-toggle" 
                className="theme-toggle-btn"
                onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            >
                {mounted && theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
            </button>

            <a href="/signup" className="nav-cta">Get Started</a>
        </div>
    </nav>

    {/* HERO */}
    <section className="hero">
        <div className="orbit-ring">
            <div className="globe-container">
                <Globe />
            </div>
        </div>
        <div className="scan-line"></div>
        <div className="sat-dot"></div>

        <div className="hero-tag">Satellite-Powered Accountability · Kenya</div>

        <h1>
            Infrastructure<br />
            <em>Audited</em> From<br />
            <span className="outline">Above</span>
        </h1>

        <p className="hero-sub">
            Oneka uses satellite imagery and geospatial intelligence to independently verify public infrastructure
            projects across Kenya — making corruption visible, and accountability inescapable.
        </p>

        <div className="hero-actions">
            <a href="#cta" className="btn-primary">Request Early Access</a>
            <a href="#how" className="btn-ghost">See How It Works</a>
        </div>

        <div className="hero-stats">
            <div className="stat-item">
                <div className="stat-num">47</div>
                <div className="stat-label">Counties Covered</div>
            </div>
            <div className="stat-item">
                <div className="stat-num">3m</div>
                <div className="stat-label">Image Resolution</div>
            </div>
            <div className="stat-item">
                <div className="stat-num">Real-Time</div>
                <div className="stat-label">Change Detection</div>
            </div>
        </div>
    </section>

    {/* MARQUEE */}
    <div className="marquee-wrap">
        <div className="marquee-track">
            <span className="marquee-item"><span>◈</span> Roads &amp; Highways</span>
            <span className="marquee-item"><span>◈</span> Water Infrastructure</span>
            <span className="marquee-item"><span>◈</span> Schools &amp; Hospitals</span>
            <span className="marquee-item"><span>◈</span> Bridges &amp; Dams</span>
            <span className="marquee-item"><span>◈</span> Housing Projects</span>
            <span className="marquee-item"><span>◈</span> Public Markets</span>
            <span className="marquee-item"><span>◈</span> Energy Infrastructure</span>
            <span className="marquee-item"><span>◈</span> Roads &amp; Highways</span>
            <span className="marquee-item"><span>◈</span> Water Infrastructure</span>
            <span className="marquee-item"><span>◈</span> Schools &amp; Hospitals</span>
            <span className="marquee-item"><span>◈</span> Bridges &amp; Dams</span>
            <span className="marquee-item"><span>◈</span> Housing Projects</span>
            <span className="marquee-item"><span>◈</span> Public Markets</span>
            <span className="marquee-item"><span>◈</span> Energy Infrastructure</span>
        </div>
    </div>

    {/* PROBLEM */}
    <section className="section" id="problem">
        <div className="section-label">The Problem</div>
        <div className="problem-grid">
            <div className="problem-text fade-in">
                <h2>Billions Lost to Ghost Projects &amp; Inflated Contracts</h2>
                <p>
                    Kenya loses an estimated KES 2 trillion to corruption annually. A significant portion is buried in
                    public infrastructure — phantom roads, half-built schools, inflated contracts, and projects that
                    exist only on paper. Traditional audits are slow, expensive, and easily manipulated.
                </p>
                <p style={{ marginTop: "1.2rem" }}>
                    Oneka changes the equation. Satellites don't take bribes.
                </p>
            </div>
            <div className="problem-cards fade-in">
                <div className="p-card">
                    <div className="p-card-icon">🛣️</div>
                    <div>
                        <h4>Ghost Road Projects</h4>
                        <p>Roads approved, funded, and reported as complete — with no physical evidence from above.
                            Satellite comparison reveals the truth.</p>
                    </div>
                </div>
                <div className="p-card">
                    <div className="p-card-icon">🏫</div>
                    <div>
                        <h4>Incomplete Public Works</h4>
                        <p>Schools and clinics stalled mid-construction for years while funds are fully disbursed and
                            contracts marked complete.</p>
                    </div>
                </div>
                <div className="p-card">
                    <div className="p-card-icon">💧</div>
                    <div>
                        <h4>Water Project Failures</h4>
                        <p>Boreholes, pipelines, and dams funded multiple times over, with minimal or no change on the
                            ground between audit cycles.</p>
                    </div>
                </div>
                <div className="p-card">
                    <div className="p-card-icon">📋</div>
                    <div>
                        <h4>Slow, Opaque Auditing</h4>
                        <p>The Auditor General's process takes years. By the time irregularities surface, funds are gone
                            and evidence is buried.</p>
                    </div>
                </div>
            </div>
        </div>
    </section>

    {/* HOW IT WORKS */}
    <section className="section how-section" id="how">
        <div className="section-label">How It Works</div>
        <h2 style={{ fontFamily: "var(--font-sans)", fontWeight: 700, fontSize: "clamp(1.8rem, 3vw, 2.6rem)", letterSpacing: "-0.02em" }}
            className="fade-in">
            From Contract Award to Ground Truth — Automatically
        </h2>
        <div className="steps-grid">
            <div className="step fade-in">
                <div className="step-num">STEP 01</div>
                <span className="step-icon">📡</span>
                <h3>Ingest Contract Data</h3>
                <p>We pull procurement records from IFMIS, NG-CDF portals, county budgets, and public tender notices —
                    building a georeferenced database of funded projects.</p>
            </div>
            <div className="step fade-in">
                <div className="step-num">STEP 02</div>
                <span className="step-icon">🛰️</span>
                <h3>Acquire Satellite Imagery</h3>
                <p>Multi-temporal satellite passes (Sentinel-2, Planet, and commercial providers) capture before,
                    during, and after imagery tied to project timelines.</p>
            </div>
            <div className="step fade-in">
                <div className="step-num">STEP 03</div>
                <span className="step-icon">🔬</span>
                <h3>Analyse &amp; Score</h3>
                <p>Our change-detection algorithms and trained ML models compare physical reality on the ground against
                    reported progress and disbursement records.</p>
            </div>
            <div className="step fade-in">
                <div className="step-num">STEP 04</div>
                <span className="step-icon">📊</span>
                <h3>Publish Audit Reports</h3>
                <p>Findings are published as open, georeferenced audit reports — available to journalists, civil
                    society, county assemblies, and the EACC.</p>
            </div>
        </div>
    </section>

    {/* FEATURES */}
    <section className="section" id="features">
        <div className="section-label">Platform Capabilities</div>
        <h2 style={{ fontFamily: "var(--font-sans)", fontWeight: 700, fontSize: "clamp(1.8rem, 3vw, 2.6rem)", letterSpacing: "-0.02em" }}
            className="fade-in">
            A Full Intelligence Stack for Infrastructure Oversight
        </h2>
        <div className="features-grid fade-in" style={{ marginTop: "4rem" }}>
            <div className="feat-card">
                <div className="feat-tag">Detection</div>
                <h3>Change Detection Engine</h3>
                <p>Pixel-level comparison across time-series imagery flags anomalies — stalled sites, misreported
                    progress, and environmental encroachment.</p>
            </div>
            <div className="feat-card">
                <div className="feat-tag">Geospatial</div>
                <h3>Interactive Audit Map</h3>
                <p>A national, filterable map showing every flagged project by county, sector, contracting authority,
                    and risk level — with evidence attached.</p>
            </div>
            <div className="feat-card">
                <div className="feat-tag">Data</div>
                <h3>Procurement Intelligence</h3>
                <p>Cross-references government spend data with physical outcomes. Identifies patterns of repeat
                    contractors with anomalous delivery records.</p>
            </div>
            <div className="feat-card">
                <div className="feat-tag">Reporting</div>
                <h3>Open Audit Reports</h3>
                <p>Machine-readable, legally citable reports with satellite evidence, GPS coordinates, and annotated
                    imagery — built for journalists and prosecutors.</p>
            </div>
            <div className="feat-card">
                <div className="feat-tag">Alerts</div>
                <h3>Real-Time Notifications</h3>
                <p>Subscribe to alerts when a project in your constituency shows signs of stagnation, abandonment, or
                    irregular earthwork activity.</p>
            </div>
            <div className="feat-card">
                <div className="feat-tag">API</div>
                <h3>Developer &amp; NGO API</h3>
                <p>Programmatic access to Oneka's dataset for civil society organizations, researchers, and oversight
                    bodies building on top of our platform.</p>
            </div>
        </div>
    </section>

    {/* DATA VISUAL */}
    <section className="data-section">
        <div className="data-inner">
            <div className="terminal fade-in">
                <div className="terminal-bar">
                    <div className="t-dot" style={{ background: "var(--oneka-red)" }}></div>
                    <div className="t-dot" style={{ background: "var(--oneka-amber)" }}></div>
                    <div className="t-dot" style={{ background: "var(--oneka-green)" }}></div>
                    <span
                            style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--muted-foreground)', marginLeft: '0.5rem' }}>oneka-audit
                        — project scan</span>
                </div>
                <div className="terminal-body">
                    <div className="t-muted">$ oneka scan --county=Nairobi --sector=roads --year=2023</div>
                    <div style={{ marginTop: "0.8rem" }} className="t-green">► Fetching procurement records...</div>
                    <div className="t-muted"> Found 47 road contracts · KES 12.4B disbursed</div>
                    <div style={{ marginTop: "0.5rem" }} className="t-green">► Acquiring satellite imagery (2022→2024)...</div>
                    <div className="t-muted"> 12 Sentinel-2 passes · 4 Planet snapshots</div>
                    <div style={{ marginTop: "0.5rem" }} className="t-green">► Running change detection model...</div>
                    <div className="t-muted"> Baseline diff: complete</div>
                    <div className="t-muted"> Road surface classifier: v2.4.1</div>
                    <div style={{ marginTop: "0.8rem" }} className="t-amber">⚠ ANOMALIES DETECTED</div>
                    <div style={{ marginTop: "0.4rem", paddingLeft: "1.2rem" }}>
                        <div className="t-red">✗ Thika Superhighway Expansion [ID: NCB-2023-0041]</div>
                        <div className="t-muted" style={{ paddingLeft: "1.2rem" }}>Reported: 94% complete · Observed: ~31%
                            complete</div>
                        <div className="t-muted" style={{ paddingLeft: "1.2rem" }}>Δ KES 2.1B — flagged for review</div>
                    </div>
                    <div style={{ marginTop: "0.5rem", paddingLeft: "1.2rem" }}>
                        <div className="t-red">✗ Eastleigh Access Road [ID: NCB-2023-0089]</div>
                        <div className="t-muted" style={{ paddingLeft: "1.2rem" }}>Reported: completed · Observed: no change
                        </div>
                        <div className="t-muted" style={{ paddingLeft: "1.2rem" }}>Δ KES 340M — escalated to EACC</div>
                    </div>
                    <div style={{ marginTop: "0.8rem" }} className="t-green">► Report saved: /audits/nairobi-roads-2023.pdf</div>
                    <div style={{ marginTop: "0.5rem" }} className="t-muted">$ <span className="cursor"></span></div>
                </div>
            </div>

            <div className="data-text fade-in">
                <div className="section-label">Satellite Evidence</div>
                <h2>Ground Truth Cannot Be Faked</h2>
                <p>Every Oneka audit is backed by timestamped, georeferenced satellite imagery. Disputed findings can be
                    independently verified by any party with the coordinates and dates we publish.</p>

                <div className="data-metrics" style={{ marginTop: "2.5rem" }}>
                    <div className="metric-row">
                        <div className="metric-label">Detection Accuracy</div>
                        <div className="metric-bar">
                            <div className="metric-fill" style={{ width: "92%" }}></div>
                        </div>
                        <div className="metric-pct">92%</div>
                    </div>
                    <div className="metric-row">
                        <div className="metric-label">False Positive Rate</div>
                        <div className="metric-bar">
                            <div className="metric-fill" style={{ width: "6%", background: "var(--oneka-amber)" }}></div>
                        </div>
                        <div className="metric-pct" style={{ color: "var(--oneka-amber)" }}>6%</div>
                    </div>
                    <div className="metric-row">
                        <div className="metric-label">Projects Auditable</div>
                        <div className="metric-bar">
                            <div className="metric-fill" style={{ width: "85%" }}></div>
                        </div>
                        <div className="metric-pct">85%</div>
                    </div>
                    <div className="metric-row">
                        <div className="metric-label">Avg. Audit Turnaround</div>
                        <div className="metric-bar">
                            <div className="metric-fill" style={{ width: "70%" }}></div>
                        </div>
                        <div className="metric-pct">72hrs</div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    {/* IMPACT */}
    <section className="impact-section" id="impact">
        <div className="section-label">Projected Impact</div>
        <h2 style={{ fontFamily: "var(--font-sans)", fontWeight: 700, fontSize: "clamp(1.8rem, 3vw, 2.6rem)", letterSpacing: "-0.02em", maxWidth: "22ch" }}
            className="fade-in">
            What Radical Transparency Does to Corruption
        </h2>
        <div className="impact-grid">
            <div className="impact-card fade-in">
                <div className="impact-num">KES 2T</div>
                <h4>Annual Corruption Cost</h4>
                <p>Kenya loses an estimated two trillion shillings annually to corruption. Infrastructure procurement
                    accounts for a substantial fraction of this figure.</p>
            </div>
            <div className="impact-card fade-in">
                <div className="impact-num">47</div>
                <h4>Counties Under Watch</h4>
                <p>From Turkana to Mombasa, Oneka's satellite coverage spans all 47 counties — independent of county
                    government cooperation or access.</p>
            </div>
            <div className="impact-card fade-in">
                <div className="impact-num">100%</div>
                <h4>Open Public Access</h4>
                <p>All audit findings are open, free, and searchable by citizens, journalists, watchdogs, Members of
                    Parliament, and county assemblies.</p>
            </div>
        </div>
    </section>

    {/* CTA */}
    <section className="cta-section" id="cta">
        <div className="section-label" style={{ textAlign: "center", display: "block" }}>Get Involved</div>
        <h2 className="fade-in">
            The Sky Doesn't Lie. Let's Prove It.
        </h2>
        <p className="fade-in">
            We're looking for civil society partners, investigative journalists, government accountability allies, and
            technical collaborators to help launch Oneka's first full audit cycle.
        </p>
        <div className="cta-btns fade-in">
            <a href="mailto:hello@oneka.ke" className="btn-primary">Partner With Us</a>
            <a href="mailto:data@oneka.ke" className="btn-ghost">Request API Access</a>
        </div>
    </section>

    {/* FOOTER */}
    <footer>
        <div className="footer-logo">ONEKA</div>
        <div className="footer-copy">© {getCurrentYear()} Oneka · Nairobi, Kenya · Built for accountability</div>
        <ul className="footer-links">
            <li><a href="#">About</a></li>
            <li><a href="#">Methodology</a></li>
            <li><a href="#">Reports</a></li>
            <li><a href="#">Contact</a></li>
        </ul>
    </footer>

    
    </main>
  );
}
