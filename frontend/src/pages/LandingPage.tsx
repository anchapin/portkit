import React, { useState } from 'react';
import './LandingPage.css';

const features = [
  {
    icon: '⚡',
    title: 'Automated Conversion',
    description:
      'Handles the tedious 60-80% of Java to Bedrock work automatically. Textures, models, recipes, entities and more.',
  },
  {
    icon: '📊',
    title: 'Detailed Conversion Report',
    description:
      'Clear report shows exactly what converted and what needs manual work. No guesswork.',
  },
  {
    icon: '🎯',
    title: 'Professional-Grade Output',
    description:
      'Marketplace-ready .mcaddon files that meet Microsoft submission standards.',
  },
  {
    icon: '🔧',
    title: 'Smart AI Assumptions',
    description:
      'Intelligent handling of ambiguous cases with documented fallback decisions.',
  },
];

const steps = [
  { number: '1', title: 'Upload', description: 'Drop your Java mod JAR file' },
  { number: '2', title: 'Convert', description: 'AI processes the conversion' },
  {
    number: '3',
    title: 'Review Report',
    description: 'See coverage breakdown',
  },
  {
    number: '4',
    title: 'Finish Manual',
    description: 'Complete remaining work',
  },
];

const faqs = [
  {
    question: 'What about IP and licensing?',
    answer:
      "Portkit processes your mod locally. We don't store or retain your files. You retain all rights to your converted content.",
  },
  {
    question: 'What quality should I expect?',
    answer:
      'Most mods achieve 60-80% automatic coverage. The detailed report shows exactly what needs review. Complex mods may require more manual work.',
  },
  {
    question: 'What manual work remains?',
    answer:
      'Typically: custom textures, advanced AI behaviors, complex recipe chains, and 3rd party mod integrations. The report pinpoints exactly what.',
  },
  {
    question: 'When will Portkit launch?',
    answer:
      "We're currently in closed testing. Join the waitlist and we'll let you know as soon as we're ready to onboard new users.",
  },
];

const footerLinks = {
  legal: [
    { label: 'Terms of Service', href: '/terms' },
    { label: 'Privacy Policy', href: '/privacy' },
    { label: 'Cookie Policy', href: '/cookies' },
    { label: 'IP Policy', href: '/ip-policy' },
    { label: 'Do Not Sell My Personal Information', href: '/privacy#ccpa' },
  ],
  social: [
    { label: 'GitHub', href: 'https://github.com/anchapin/portkit' },
    { label: 'Discord', href: 'https://discord.gg/modporter' },
    { label: 'Twitter', href: 'https://twitter.com/modporterai' },
  ],
  support: [{ label: 'Status', href: '/status' }],
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
  ? import.meta.env.VITE_API_BASE_URL + '/api/v1'
  : import.meta.env.VITE_API_URL
    ? import.meta.env.VITE_API_URL.replace(/\/api\/v1$/, '') + '/api/v1'
    : '/api/v1';

const LandingPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [status, setStatus] = useState<
    'idle' | 'loading' | 'success' | 'error'
  >('idle');
  const [message, setMessage] = useState('');
  const [expandedFaq, setExpandedFaq] = useState<number | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;

    setStatus('loading');
    try {
      const response = await fetch(`${API_BASE_URL}/waitlist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          name: name || undefined,
          source: 'landing-page',
        }),
      });

      if (!response.ok) {
        throw new Error('Something went wrong. Please try again.');
      }

      const data = await response.json();
      setStatus('success');
      setMessage(data.message);
      setEmail('');
      setName('');
    } catch (err) {
      setStatus('error');
      setMessage(
        err instanceof Error
          ? err.message
          : 'Something went wrong. Please try again.'
      );
    }
  };

  return (
    <div className="landing-page">
      <nav className="landing-nav">
        <div className="nav-container">
          <div className="nav-logo">
            <span className="logo-icon">🎮</span>
            <span className="logo-text">Portkit</span>
          </div>
          <div className="nav-links">
            <a href="#features">Features</a>
            <a href="#how-it-works">How It Works</a>
            <a href="#faq">FAQ</a>
          </div>
        </div>
      </nav>

      <section className="hero-section">
        <div className="hero-container">
          <div className="hero-badge">Coming Soon — Join the Waitlist</div>
          <div className="hero-version-badge">
            Converts Java 1.18-1.21 → Bedrock 1.21.0
          </div>
          <h1 className="hero-title">
            Get Your Java Mods on the
            <br />
            <span className="hero-highlight">Bedrock Marketplace Faster</span>
          </h1>
          <p className="hero-subtitle">
            Portkit handles 60-80% of Java to Bedrock conversion automatically.
            Detailed reports show exactly what needs manual work — no guesswork.
          </p>

          <form className="waitlist-form" onSubmit={handleSubmit}>
            {status !== 'success' ? (
              <>
                <div className="waitlist-fields">
                  <input
                    type="text"
                    className="waitlist-input"
                    placeholder="Your name (optional)"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    disabled={status === 'loading'}
                  />
                  <div className="waitlist-email-row">
                    <input
                      type="email"
                      className="waitlist-input"
                      placeholder="your@email.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      disabled={status === 'loading'}
                    />
                    <button
                      type="submit"
                      className="waitlist-submit"
                      disabled={status === 'loading'}
                    >
                      {status === 'loading' ? 'Joining...' : 'Join Waitlist'}
                    </button>
                  </div>
                </div>
                {status === 'error' && (
                  <p className="waitlist-error">{message}</p>
                )}
              </>
            ) : (
              <div className="waitlist-success">
                <span className="waitlist-success-icon">✓</span>
                <p>{message}</p>
              </div>
            )}
          </form>

          <div className="hero-stats">
            <div className="stat">
              <span className="stat-value">68%</span>
              <span className="stat-label">Avg. Texture Coverage</span>
            </div>
            <div className="stat-divider" />
            <div className="stat">
              <span className="stat-value">30+</span>
              <span className="stat-label">Mods Tested</span>
            </div>
            <div className="stat-divider" />
            <div className="stat">
              <span className="stat-value">60-80%</span>
              <span className="stat-label">Time Saved</span>
            </div>
          </div>
        </div>
      </section>

      <section id="features" className="features-section">
        <div className="section-container">
          <h2 className="section-title">Everything You Need to Go to Market</h2>
          <p className="section-subtitle">
            Built for professional modders who need reliable, repeatable
            conversion
          </p>
          <div className="features-grid">
            {features.map((feature, index) => (
              <div key={index} className="feature-card">
                <div className="feature-icon">{feature.icon}</div>
                <h3 className="feature-title">{feature.title}</h3>
                <p className="feature-description">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="how-it-works" className="how-it-works-section">
        <div className="section-container">
          <h2 className="section-title">Simple Workflow</h2>
          <p className="section-subtitle">
            From upload to marketplace-ready in four steps
          </p>
          <div className="steps-container">
            {steps.map((step, index) => (
              <div key={index} className="step-card">
                <div className="step-number">{step.number}</div>
                <h3 className="step-title">{step.title}</h3>
                <p className="step-description">{step.description}</p>
                {index < steps.length - 1 && (
                  <div className="step-arrow">→</div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="faq" className="faq-section">
        <div className="section-container">
          <h2 className="section-title">Frequently Asked Questions</h2>
          <div className="faq-list">
            {faqs.map((faq, index) => (
              <div key={index} className="faq-item">
                <button
                  className={`faq-question ${expandedFaq === index ? 'expanded' : ''}`}
                  onClick={() =>
                    setExpandedFaq(expandedFaq === index ? null : index)
                  }
                >
                  {faq.question}
                  <span
                    className={`faq-icon ${expandedFaq === index ? 'rotated' : ''}`}
                  >
                    ▼
                  </span>
                </button>
                {expandedFaq === index && (
                  <div className="faq-answer">
                    <p>{faq.answer}</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="waitlist-cta-section">
        <div className="section-container">
          <h2 className="section-title">Be First in Line</h2>
          <p className="section-subtitle">
            Join the waitlist and get early access when we launch
          </p>
          <form
            className="waitlist-form waitlist-form-center"
            onSubmit={handleSubmit}
          >
            {status !== 'success' ? (
              <>
                <div className="waitlist-email-row">
                  <input
                    type="email"
                    className="waitlist-input"
                    placeholder="your@email.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    disabled={status === 'loading'}
                  />
                  <button
                    type="submit"
                    className="waitlist-submit"
                    disabled={status === 'loading'}
                  >
                    {status === 'loading' ? 'Joining...' : 'Join Waitlist'}
                  </button>
                </div>
              </>
            ) : (
              <div className="waitlist-success">
                <span className="waitlist-success-icon">✓</span>
                <p>{message}</p>
              </div>
            )}
          </form>
        </div>
      </section>

      <footer className="landing-footer">
        <div className="footer-container">
          <div className="footer-brand">
            <div className="footer-logo">
              <span className="logo-icon">🎮</span>
              <span className="logo-text">Portkit</span>
            </div>
            <p className="footer-tagline">
              Java to Bedrock conversion for the Minecraft community.
            </p>
          </div>
          <div className="footer-links-grid">
            <div className="footer-column">
              <h4>Legal</h4>
              <ul>
                {footerLinks.legal.map((link, index) => (
                  <li key={index}>
                    <a href={link.href}>{link.label}</a>
                  </li>
                ))}
              </ul>
            </div>
            <div className="footer-column">
              <h4>Community</h4>
              <ul>
                {footerLinks.social.map((link, index) => (
                  <li key={index}>
                    <a
                      href={link.href}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
            <div className="footer-column">
              <h4>Support</h4>
              <ul>
                {footerLinks.support.map((link, index) => (
                  <li key={index}>
                    <a href={link.href}>{link.label}</a>
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <div className="footer-bottom">
            <p>&copy; 2026 Portkit. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
