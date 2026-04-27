import { useState, useEffect } from 'react';
import { memo, useRef } from 'react';
import L from 'leaflet';
// @ts-ignore
import 'leaflet/dist/leaflet.css';
import { mesh } from 'topojson-client';
import land110m from 'world-atlas/land-110m.json';
import { 
  Cpu, 
  Activity, 
  Globe,
  ArrowRight,
  BrainCircuit,
  ChevronRight,
  Database,
  ArrowUpRight,
  Shield,
  Menu,
  X
} from 'lucide-react';

const splitAntimeridianSegments = (lines: GeoJSON.Position[][]): GeoJSON.Position[][] =>
  lines.flatMap((line) => {
    const segments: GeoJSON.Position[][] = [];
    let currentSegment: GeoJSON.Position[] = [];

    line.forEach((point) => {
      const previousPoint = currentSegment[currentSegment.length - 1];

      if (previousPoint && Math.abs(point[0] - previousPoint[0]) > 180) {
        if (currentSegment.length > 1) {
          segments.push(currentSegment);
        }
        currentSegment = [point];
        return;
      }

      currentSegment.push(point);
    });

    if (currentSegment.length > 1) {
      segments.push(currentSegment);
    }

    return segments;
  });

const createLandOutline = (): GeoJSON.MultiLineString => {
  const topology = land110m as unknown as {
    objects: {
      countries?: unknown;
      land?: unknown;
    };
  };
  const landObject = topology.objects.land ?? topology.objects.countries;

  if (!landObject) {
    return {
      type: 'MultiLineString',
      coordinates: [],
    };
  }

  const outline = mesh(
    land110m as unknown as Parameters<typeof mesh>[0],
    landObject as Parameters<typeof mesh>[1],
  ) as unknown as GeoJSON.LineString | GeoJSON.MultiLineString;

  const lines = outline.type === 'LineString' ? [outline.coordinates] : outline.coordinates;

  return {
    type: 'MultiLineString',
    coordinates: splitAntimeridianSegments(lines),
  };
};

const IntroWorldMap = memo(() => {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);

  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) {
      return;
    }

    const mapCenter: L.LatLngExpression = [12, 0];
    const worldBounds: L.LatLngBoundsExpression = [
      [-85, -180],
      [85, 180],
    ];
    const initialZoom = window.innerWidth < 768 ? 1 : 2;
    const map = L.map(mapContainerRef.current, {
      attributionControl: false,
      boxZoom: false,
      doubleClickZoom: false,
      dragging: false,
      fadeAnimation: false,
      keyboard: false,
      markerZoomAnimation: false,
      maxBounds: worldBounds,
      maxBoundsViscosity: 1,
      scrollWheelZoom: false,
      touchZoom: false,
      worldCopyJump: false,
      zoomAnimation: false,
      zoomControl: false,
      zoomSnap: 0.25,
    }).setView(mapCenter, initialZoom);

    const landOutline = createLandOutline();

    L.geoJSON(landOutline, {
      interactive: false,
      style: {
        className: 'intro-continent-glow',
        color: '#ffffff',
        fill: false,
        opacity: 0.62,
        weight: 2.8,
      },
    }).addTo(map);

    L.geoJSON(landOutline, {
      interactive: false,
      style: {
        className: 'intro-continent-line',
        color: '#ffffff',
        fill: false,
        opacity: 0.96,
        weight: 0.95,
      },
    }).addTo(map);

    mapRef.current = map;

    const resizeMap = () => {
      const nextZoom = window.innerWidth < 768 ? 1 : 2;
      map.setView(mapCenter, nextZoom, { animate: false });
      map.invalidateSize();
    };

    window.addEventListener('resize', resizeMap);
    window.setTimeout(() => map.invalidateSize(), 80);

    return () => {
      window.removeEventListener('resize', resizeMap);
      map.remove();
      mapRef.current = null;
    };
  }, []);

  return (
    <div className="intro-map-shell" aria-hidden="true">
      <div ref={mapContainerRef} className="intro-world-map" />
      <span className="intro-map-attribution">
        © Stadia Maps © Stamen © OpenMapTiles © OpenStreetMap
      </span>
    </div>
  );
});

const App = () => {
  const [formType, setFormType] = useState('volunteer');
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const introOverlayRef = useRef<HTMLDivElement | null>(null);
  const introMapLayerRef = useRef<HTMLDivElement | null>(null);
  const auraRef = useRef<HTMLDivElement | null>(null);
  const leftCurtainRef = useRef<HTMLDivElement | null>(null);
  const rightCurtainRef = useRef<HTMLDivElement | null>(null);
  const scrollHintRef = useRef<HTMLDivElement | null>(null);
  const navRef = useRef<HTMLElement | null>(null);
  const heroRef = useRef<HTMLElement | null>(null);

  // Monitoramento do scroll para o efeito cortina suavizado
  useEffect(() => {
    let scrollFrame = 0;
    let mouseFrame = 0;
    let nextMousePos = { x: 0, y: 0 };

    const applyScrollProgress = (progress: number) => {
      if (introOverlayRef.current) {
        introOverlayRef.current.style.opacity = `${1 - progress * 1.5}`;
        introOverlayRef.current.style.visibility = progress >= 0.95 ? 'hidden' : 'visible';
      }

      if (introMapLayerRef.current) {
        introMapLayerRef.current.style.opacity = `${Math.max(0, 0.62 - progress * 0.82)}`;
        introMapLayerRef.current.style.transform = `translate3d(0,0,0) scale(${1 + progress * 0.02})`;
      }

      if (leftCurtainRef.current) {
        leftCurtainRef.current.style.transform = `translate3d(${-progress * 100}%,0,0)`;
      }

      if (rightCurtainRef.current) {
        rightCurtainRef.current.style.transform = `translate3d(${progress * 100}%,0,0)`;
      }

      if (scrollHintRef.current) {
        scrollHintRef.current.style.opacity = `${1 - progress * 5}`;
      }

      if (navRef.current) {
        const isVisible = progress > 0.4;
        navRef.current.style.opacity = isVisible ? '1' : '0';
        navRef.current.style.transform = `translate3d(0, ${isVisible ? 0 : -20}px, 0)`;
      }

      if (heroRef.current) {
        heroRef.current.style.opacity = `${Math.max(0, (progress - 0.2) * 1.5)}`;
        heroRef.current.style.transform = `translate3d(0, ${(1 - progress) * 30}px, 0)`;
      }
    };

    const handleScroll = () => {
      if (scrollFrame) {
        return;
      }

      scrollFrame = window.requestAnimationFrame(() => {
        const currentScroll = window.scrollY;
        const progress = Math.min(currentScroll / 1000, 1);
        applyScrollProgress(progress);
        scrollFrame = 0;
      });
    };

    const handleMouseMove = (e: MouseEvent) => {
      // Atualiza a posição do mouse para o efeito de fumaça
      nextMousePos = { x: e.clientX, y: e.clientY };

      if (mouseFrame) {
        return;
      }

      mouseFrame = window.requestAnimationFrame(() => {
        if (auraRef.current) {
          auraRef.current.style.transform = `translate3d(${nextMousePos.x - 300}px, ${nextMousePos.y - 300}px, 0)`;
        }
        mouseFrame = 0;
      });
    };

    handleScroll();

    window.addEventListener('scroll', handleScroll, { passive: true });
    window.addEventListener('mousemove', handleMouseMove, { passive: true });
    
    return () => {
      window.removeEventListener('scroll', handleScroll);
      window.removeEventListener('mousemove', handleMouseMove);
      if (scrollFrame) {
        window.cancelAnimationFrame(scrollFrame);
      }
      if (mouseFrame) {
        window.cancelAnimationFrame(mouseFrame);
      }
    };
  }, []);

  useEffect(() => {
    const revealElements = Array.from(document.querySelectorAll<HTMLElement>('[data-reveal]'));
    const pendingRevealElements = new Set(revealElements);
    let revealFrame = 0;

    if (!('IntersectionObserver' in window)) {
      revealElements.forEach((element) => element.classList.add('is-visible'));
      return;
    }

    const markVisible = (element: HTMLElement, observer?: IntersectionObserver) => {
      element.classList.add('is-visible');
      pendingRevealElements.delete(element);
      observer?.unobserve(element);
    };

    const revealIfNearViewport = () => {
      if (revealFrame || pendingRevealElements.size === 0) {
        return;
      }

      revealFrame = window.requestAnimationFrame(() => {
      const viewportHeight = window.innerHeight || document.documentElement.clientHeight;

      Array.from(pendingRevealElements).forEach((element) => {
        const rect = element.getBoundingClientRect();
        const revealOffset = window.innerWidth < 768 ? viewportHeight * 0.35 : viewportHeight * 0.18;

        if (rect.top <= viewportHeight + revealOffset && rect.bottom >= -revealOffset) {
          markVisible(element, observer);
        }
      });
        revealFrame = 0;
      });
    };

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            markVisible(entry.target as HTMLElement, observer);
          }
        });
      },
      {
        threshold: window.innerWidth < 768 ? 0.01 : 0.14,
        rootMargin: window.innerWidth < 768 ? '0px 0px 28% 0px' : '0px 0px 12% 0px',
      },
    );

    revealElements.forEach((element) => observer.observe(element));
    revealIfNearViewport();

    window.addEventListener('scroll', revealIfNearViewport, { passive: true });
    window.addEventListener('resize', revealIfNearViewport);

    return () => {
      observer.disconnect();
      window.removeEventListener('scroll', revealIfNearViewport);
      window.removeEventListener('resize', revealIfNearViewport);
      if (revealFrame) {
        window.cancelAnimationFrame(revealFrame);
      }
    };
  }, []);

  const scrollToSection = (id: string) => {
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
      setIsMobileMenuOpen(false);
    }
  };

  const handleRegistrationSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    window.location.href = 'https://hackathon.albuqr.com/';
  };

  return (
    <div className="crisis-page bg-[#0a0a0a] font-sans text-[#f4f4f4] selection:bg-blue-600/30">
      
      {/* EFEITO CORTINA SUAVIZADO COM EFEITO DE FUMAÇA NO CURSOR */}
      <div 
        ref={introOverlayRef}
        className="fixed inset-0 z-[100] pointer-events-none overflow-hidden will-change-[opacity,visibility]"
        style={{ opacity: 1, visibility: 'visible' }}
      >
        <div
          ref={introMapLayerRef}
          className="absolute inset-0 z-0 will-change-[opacity,transform] transform-gpu"
          style={{ opacity: 0.62, transform: 'translate3d(0,0,0) scale(1)' }}
        >
          <IntroWorldMap />
        </div>

        {/* Efeito de Fumaça/Aura Suave (Segue o Mouse) */}
        <div 
          ref={auraRef}
          className="absolute left-0 top-0 z-[3] w-[600px] h-[600px] rounded-full pointer-events-none opacity-40 md:opacity-60 will-change-transform transform-gpu"
          style={{ 
            transform: 'translate3d(-300px, -300px, 0)',
            background: 'radial-gradient(circle, rgba(0,98,255,0.08) 0%, rgba(0,0,0,0) 70%)',
            filter: 'blur(40px)',
            mixBlendMode: 'screen'
          }}
        />

        {/* Painel Esquerdo */}
        <div 
          ref={leftCurtainRef}
          className="absolute inset-y-0 left-0 z-[2] bg-[#050505]/80 w-1/2 flex items-center justify-end will-change-transform transform-gpu"
          style={{ transform: 'translate3d(0,0,0)' }}
        >
          <div className="pr-8 md:pr-16 text-right">
            <h2 className="intro-crisis-word text-6xl sm:text-7xl md:text-[10rem] font-black tracking-tighter text-white uppercase select-none leading-none">Cri</h2>
            <p className="text-[8px] sm:text-[9px] tracking-[0.45em] sm:tracking-[0.8em] text-[#525252] uppercase mt-2 mr-1 font-medium">Humanitarian</p>
          </div>
        </div>

        {/* Painel Direito */}
        <div 
          ref={rightCurtainRef}
          className="absolute inset-y-0 right-0 z-[2] bg-[#050505]/80 w-1/2 flex items-center justify-start will-change-transform transform-gpu"
          style={{ transform: 'translate3d(0,0,0)' }}
        >
          <div className="pl-8 md:pl-16">
            <h2 className="intro-crisis-word text-6xl sm:text-7xl md:text-[10rem] font-black tracking-tighter text-white uppercase select-none leading-none">sis</h2>
            <p className="text-[8px] sm:text-[9px] tracking-[0.45em] sm:tracking-[0.8em] text-[#525252] uppercase mt-2 ml-1 font-medium">Intelligence</p>
          </div>
        </div>

        {/* Indicador de Ação Minimalista */}
        <div 
          ref={scrollHintRef}
          className="absolute inset-0 z-[4] flex flex-col items-center justify-end pb-24 transition-opacity duration-700"
          style={{ opacity: 1 }}
        >
          <div className="flex flex-col items-center gap-4 text-[#393939] text-[10px] tracking-[1em] uppercase font-bold">
             <span className="animate-pulse">Scroll</span>
             <span className="intro-scroll-arrow" aria-hidden="true">↓</span>
             <div className="w-[1px] h-12 bg-gradient-to-b from-[#393939] to-transparent"></div>
          </div>
        </div>
      </div>

      {/* Navbar - Carbon Minimalist */}
      <nav 
        ref={navRef}
        className="fixed w-full bg-[#0a0a0a]/95 backdrop-blur-md z-50 border-b border-[#262626] transition-all duration-700"
        style={{ opacity: 0, transform: 'translate3d(0, -20px, 0)' }}
      >
        <div className="max-w-[1584px] mx-auto px-4 md:px-12 h-14 flex items-center justify-between gap-4">
          <div className="flex items-center gap-8 xl:gap-16">
            <span className="text-xl font-bold tracking-tighter text-white uppercase select-none cursor-default">
              Crisis
            </span>
            <div className="hidden lg:flex gap-10 text-[13px] font-medium text-[#a8a8a8]">
              <button onClick={() => scrollToSection('mission')} className="hover:text-white transition-colors uppercase tracking-[0.2em] text-[11px]">O Projeto</button>
              <button onClick={() => scrollToSection('technology')} className="hover:text-white transition-colors uppercase tracking-[0.2em] text-[11px]">Arquitetura</button>
              <button onClick={() => scrollToSection('how-it-works')} className="hover:text-white transition-colors uppercase tracking-[0.2em] text-[11px]">Funcionamento</button>
              <button onClick={() => scrollToSection('governance')} className="hover:text-white transition-colors uppercase tracking-[0.2em] text-[11px]">Governança</button>
            </div>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <button 
              onClick={() => scrollToSection('registration-form')}
              className="bg-[#0062ff] text-white px-4 sm:px-6 py-2.5 text-[10px] sm:text-[11px] font-bold hover:bg-[#0052d4] transition-all uppercase tracking-widest flex items-center gap-2"
            >
              Acesso <ArrowUpRight size={14} />
            </button>
            <button
              type="button"
              aria-label={isMobileMenuOpen ? 'Fechar menu' : 'Abrir menu'}
              aria-expanded={isMobileMenuOpen}
              onClick={() => setIsMobileMenuOpen((current) => !current)}
              className="lg:hidden h-10 w-10 border border-[#262626] text-white flex items-center justify-center hover:border-blue-500 transition-all"
            >
              {isMobileMenuOpen ? <X size={18} /> : <Menu size={18} />}
            </button>
          </div>
        </div>
        {isMobileMenuOpen && (
          <div className="lg:hidden border-t border-[#262626] bg-[#0a0a0a]/98 backdrop-blur-md px-4 py-4">
            <div className="grid gap-2">
              <button onClick={() => scrollToSection('mission')} className="w-full text-left px-4 py-4 text-[#a8a8a8] hover:text-white hover:bg-[#161616] transition-all uppercase tracking-[0.18em] text-[11px]">O Projeto</button>
              <button onClick={() => scrollToSection('technology')} className="w-full text-left px-4 py-4 text-[#a8a8a8] hover:text-white hover:bg-[#161616] transition-all uppercase tracking-[0.18em] text-[11px]">Arquitetura</button>
              <button onClick={() => scrollToSection('how-it-works')} className="w-full text-left px-4 py-4 text-[#a8a8a8] hover:text-white hover:bg-[#161616] transition-all uppercase tracking-[0.18em] text-[11px]">Funcionamento</button>
              <button onClick={() => scrollToSection('governance')} className="w-full text-left px-4 py-4 text-[#a8a8a8] hover:text-white hover:bg-[#161616] transition-all uppercase tracking-[0.18em] text-[11px]">Governança</button>
            </div>
          </div>
        )}
      </nav>

      {/* Espaçador para o efeito de scroll inicial */}
      <div className="h-[620px] md:h-[800px] bg-transparent pointer-events-none"></div>

      {/* Hero Section */}
      <header 
        ref={heroRef}
        id="mission" 
        className="relative scroll-mt-14 pt-28 pb-20 sm:pt-36 md:pt-64 md:pb-48 px-5 md:px-12 border-b border-[#262626] overflow-hidden transition-all duration-1000 ease-out"
        style={{ opacity: 0, transform: 'translate3d(0, 30px, 0)' }}
      >
        <div className="absolute inset-0 opacity-[0.03] pointer-events-none" style={{ backgroundImage: 'radial-gradient(#fff 1px, transparent 0)', backgroundSize: '60px 60px' }}></div>
        
        <div className="max-w-[1584px] mx-auto grid lg:grid-cols-12 gap-10 md:gap-16">
          <div className="lg:col-span-12 space-y-9 md:space-y-12">
            <div className="flex items-center gap-3 text-blue-500 text-[10px] sm:text-[11px] font-bold tracking-[0.24em] sm:tracking-[0.4em] uppercase">
              <div className="w-6 sm:w-8 h-[1px] bg-blue-600 shrink-0"></div>
              Orquestração de Resiliência Humanitária
            </div>
            
            <h1 className="text-[2.75rem] sm:text-6xl md:text-[100px] leading-[1.1] md:leading-[1.08] font-light tracking-tighter text-white max-w-6xl">
              Tecnologia avançada para a <br />
              <span className="font-bold text-[#0062ff]">gestão de cenários críticos</span>
            </h1>

            <div className="grid lg:grid-cols-12 gap-10 md:gap-12 pt-4 md:pt-8">
              <div className="lg:col-span-7">
                <p className="text-lg sm:text-xl md:text-2xl text-[#a8a8a8] font-light leading-relaxed">
                  Crisis é uma iniciativa estruturada para resolver o hiato de coordenação entre instituições e redes de apoio. Através do ecossistema <span className="text-white font-medium">IBM watsonx</span>, mitigamos a fragmentação operacional para garantir agilidade onde ela é vital.
                </p>
                
                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-0 mt-10 md:mt-16">
                  <button 
                    onClick={() => scrollToSection('how-it-works')}
                    className="bg-[#0062ff] text-white px-6 sm:px-8 md:px-10 py-5 flex items-center justify-between gap-8 md:gap-16 group hover:bg-[#0052d4] transition-all w-full sm:w-auto sm:min-w-[260px] md:min-w-[280px] sm:border-r border-[#004dc8]"
                  >
                    <span className="font-bold text-[12px] sm:text-[13px] md:text-[14px] uppercase tracking-[0.16em] sm:tracking-[0.2em]">Explorar o Projeto</span>
                    <ArrowRight size={20} className="group-hover:translate-x-2 transition-transform" />
                  </button>
                  <button 
                    onClick={() => scrollToSection('registration-form')}
                    className="bg-[#393939] text-white px-6 sm:px-8 md:px-10 py-5 flex items-center justify-between gap-8 md:gap-16 group hover:bg-[#474747] transition-all w-full sm:w-auto sm:min-w-[260px] md:min-w-[280px]"
                  >
                    <span className="font-bold text-[12px] sm:text-[13px] md:text-[14px] uppercase tracking-[0.16em] sm:tracking-[0.2em]">Acessar Hub</span>
                    <ChevronRight size={20} />
                  </button>
                </div>
              </div>

              <div className="lg:col-span-5 flex flex-col justify-end pb-1">
                <div className="flex items-start gap-4 p-6 bg-[#161616] border-l-4 border-blue-600">
                  <Activity className="text-blue-500 shrink-0" size={24} />
                  <div>
                    <span className="block text-[11px] font-bold text-[#f4f4f4] uppercase tracking-widest mb-1">Status do Sistema</span>
                    <p className="text-sm text-[#a8a8a8] font-light leading-snug">
                      Monitoramento agêntico de dados meteorológicos e humanitários ativos.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Propósito e Contexto */}
      <section data-reveal className="bg-[#161616] border-b border-[#262626] py-20 md:py-32 px-5 md:px-12">
        <div className="max-w-[1584px] mx-auto grid md:grid-cols-3 gap-12 md:gap-20">
          <div className="space-y-6">
            <h4 className="text-white font-bold text-[11px] uppercase tracking-[0.22em] sm:tracking-[0.3em] flex items-center gap-3">
              <div className="w-1.5 h-1.5 bg-blue-600"></div> O Desafio
            </h4>
            <p className="text-[#a8a8a8] text-base leading-relaxed font-light">
              Em situações de emergência, a fragmentação de dados e a comunicação manual retardam a mobilização de ajuda. A Crisis centraliza a inteligência para reduzir a inércia logística.
            </p>
          </div>
          <div className="space-y-6">
            <h4 className="text-white font-bold text-[11px] uppercase tracking-[0.22em] sm:tracking-[0.3em] flex items-center gap-3">
              <div className="w-1.5 h-1.5 bg-blue-600"></div> A Abordagem
            </h4>
            <p className="text-[#a8a8a8] text-base leading-relaxed font-light">
              Utilizamos inteligência agêntica para analisar vulnerabilidades sociais e climáticas em tempo real, permitindo que as instituições preparem recursos humanos de forma antecipada.
            </p>
          </div>
          <div className="space-y-6">
            <h4 className="text-white font-bold text-[11px] uppercase tracking-[0.22em] sm:tracking-[0.3em] flex items-center gap-3">
              <div className="w-1.5 h-1.5 bg-blue-600"></div> O Impacto
            </h4>
            <p className="text-[#a8a8a8] text-base leading-relaxed font-light">
              A automação dos fluxos de convocação e confirmação libera equipes humanitárias para o trabalho de campo, otimizando o aproveitamento de cada voluntário na rede.
            </p>
          </div>
        </div>
      </section>

      {/* Technology Section */}
      <section data-reveal id="technology" className="scroll-mt-14 py-24 md:py-32 px-5 md:px-12 border-b border-[#262626]">
        <div className="max-w-[1584px] mx-auto">
          <div className="mb-14 md:mb-24">
            <h2 className="text-[11px] font-bold text-blue-500 uppercase tracking-[0.28em] sm:tracking-[0.5em] mb-4">Base Tecnológica</h2>
            <h3 className="text-3xl sm:text-4xl md:text-5xl font-light text-white italic leading-[1.16]">A arquitetura da <br /> resposta inteligente.</h3>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 border-t border-[#262626]">
            {[
              { icon: BrainCircuit, title: "watsonx.ai", desc: "Processamento de Linguagem Natural para traduzir demandas complexas em categorias de ação imediata." },
              { icon: Cpu, title: "Orchestrate", desc: "Gestão autônoma de fluxos de trabalho e comunicação ativa com as redes de apoio." },
              { icon: Database, title: "Cloudant NoSQL", desc: "Armazenamento resiliente e escalável de competências, garantindo disponibilidade em qualquer cenário." },
              { icon: Globe, title: "Interface Estratégica", desc: "Sistemas de georreferenciamento para visualização estratégica de ativos e zonas de impacto." }
            ].map((tech, i) => (
              <div key={i} className="p-8 md:p-12 border-b lg:border-b-0 lg:border-r border-[#262626] hover:bg-white/[0.01] transition-all group">
                <tech.icon size={32} className="text-blue-600 mb-7 md:mb-10 group-hover:scale-110 transition-transform duration-500" />
                <h4 className="text-base md:text-lg font-bold text-white mb-5 md:mb-6 uppercase tracking-wider">{tech.title}</h4>
                <p className="text-sm text-[#a8a8a8] leading-relaxed font-light">{tech.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Project Intelligence Section */}
      <section data-reveal id="project-details" className="project-intelligence relative scroll-mt-14 py-20 sm:py-24 md:py-36 px-5 sm:px-6 md:px-12 bg-[#0a0a0a] border-b border-[#262626] overflow-hidden">
        <div className="project-grid pointer-events-none absolute inset-0"></div>
        <div className="project-scanline pointer-events-none absolute inset-x-0 top-0 h-px"></div>

        <div className="relative z-10 max-w-[1584px] mx-auto">
          <div data-reveal-item className="grid lg:grid-cols-12 gap-9 sm:gap-12 lg:gap-20 mb-14 sm:mb-20">
            <div className="lg:col-span-5">
              <h2 className="text-[11px] font-bold text-blue-500 uppercase tracking-[0.28em] sm:tracking-[0.5em] mb-6">Crisis</h2>
              <h3 className="text-[2.45rem] min-[390px]:text-4xl sm:text-5xl md:text-6xl font-light text-white leading-[1.14] sm:leading-[1.12]">
                Resposta humanitária <br className="hidden sm:block" />
                <span className="text-blue-500 italic">em tempo real.</span>
              </h3>
            </div>
            <div className="lg:col-span-7 flex items-end">
              <p className="text-base min-[390px]:text-lg sm:text-xl md:text-2xl text-[#a8a8a8] font-light leading-relaxed max-w-4xl">
                Plataforma que usa agentes de IA orquestrados pelo IBM watsonx Orchestrate para monitorar crises globais, classificar severidade e conectar automaticamente voluntários e ONGs às causas onde podem contribuir.
              </p>
            </div>
          </div>

          <div data-reveal-item className="grid md:grid-cols-3 border-y border-[#262626] mb-16 sm:mb-20 bg-[#0d0d0d]/60 backdrop-blur-sm">
            {[
              { metric: "01", title: "Monitorar", desc: "Ingere terremotos, desastres naturais, incêndios, secas e conflitos a partir de fontes externas." },
              { metric: "02", title: "Classificar", desc: "Transforma eventos brutos em crises priorizadas por tipo, severidade e risco humanitário." },
              { metric: "03", title: "Mobilizar", desc: "Cruza habilidades, localização e raio de atuação para acionar a rede certa no momento certo." }
            ].map((item, i) => (
              <div key={i} className="flow-card relative p-7 sm:p-8 md:p-10 border-b md:border-b-0 md:border-r last:border-r-0 border-[#262626] group">
                <span className="block text-blue-500 font-mono text-[11px] mb-5">{item.metric}</span>
                <h4 className="text-xl font-light text-white mb-4 group-hover:text-blue-400 transition-colors">{item.title}</h4>
                <p className="text-sm text-[#a8a8a8] leading-relaxed font-light">{item.desc}</p>
              </div>
            ))}
          </div>

          <div className="space-y-16 sm:space-y-20 md:space-y-24">
            <div data-reveal-item>
              <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-5 sm:gap-6 mb-8 sm:mb-10">
                <div>
                  <h3 className="text-2xl min-[390px]:text-3xl md:text-4xl font-light text-white mb-4">Agentes de IA</h3>
                  <p className="text-[#a8a8a8] text-sm sm:text-base leading-relaxed max-w-3xl">
                    Cada agente resolve uma etapa recorrente da crise: detecção, classificação, matching, comunicação, otimização, previsão e suporte conversacional.
                  </p>
                </div>
                <span className="text-[10px] sm:text-[11px] text-[#525252] uppercase tracking-[0.18em] sm:tracking-[0.28em] font-bold">Watsonx Orchestrate</span>
              </div>

              <div className="grid md:grid-cols-2 xl:grid-cols-3 border-t border-l border-[#262626]">
                {[
                  { name: "crisis_orchestrator", role: "Supervisor central", desc: "Recebe as requisições de chat e decide qual agente especializado acionar, funcionando como ponto de entrada da orquestração." },
                  { name: "monitoring_agent", role: "Monitoramento em tempo real", desc: "Aciona coletas USGS, GDACS, EONET e conflitos, consolidando eventos em uma lista unificada." },
                  { name: "classification_agent", role: "Priorização de severidade", desc: "Classifica eventos por tipo e severidade de 1 a 5 usando Granite, reduzindo ambiguidade operacional." },
                  { name: "matching_agent", role: "Conexão voluntário-crise", desc: "Usa embeddings Granite e distância haversine para calcular compatibilidade por habilidade, localização e raio." },
                  { name: "communication_agent", role: "Notificação automática", desc: "Envia alertas via Telegram e WhatsApp quando uma crise relevante aparece na área de atuação cadastrada." },
                  { name: "optimization_agent", role: "Balanceamento da rede", desc: "Analisa a distribuição de voluntários e sugere realocações para maximizar impacto humanitário." },
                  { name: "prediction_agent", role: "Risco futuro", desc: "Usa Granite 3.3-8B para prever riscos dos próximos 30 dias com base em histórico, clima e conflitos." },
                  { name: "volunteer_agent", role: "Chat do voluntário", desc: "Responde perguntas sobre crises próximas e orienta formas de contribuição com base no perfil do voluntário." },
                  { name: "assistant_agent", role: "Chat da ONG", desc: "Ajuda ONGs a estruturar campanhas, urgência, habilidades necessárias e descrição vinculada à crise." }
                ].map((agent, i) => (
                  <div key={i} data-reveal-item style={{ transitionDelay: `${120 + i * 35}ms` }} className="intelligence-card relative p-6 sm:p-7 md:p-8 border-r border-b border-[#262626] bg-[#0a0a0a]/80 transition-all">
                    <span className="block text-[10px] text-blue-500 font-mono mb-4 uppercase tracking-[0.12em] sm:tracking-[0.18em] break-words">{agent.name}</span>
                    <h4 className="text-base sm:text-lg text-white font-bold mb-4">{agent.role}</h4>
                    <p className="text-sm text-[#a8a8a8] leading-relaxed font-light">{agent.desc}</p>
                  </div>
                ))}
              </div>
            </div>

            <div data-reveal-item>
              <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-5 sm:gap-6 mb-8 sm:mb-10">
                <div>
                  <h3 className="text-2xl min-[390px]:text-3xl md:text-4xl font-light text-white mb-4">Ferramentas</h3>
                  <p className="text-[#a8a8a8] text-sm sm:text-base leading-relaxed max-w-3xl">
                    As tools conectam os agentes ao mundo real: coletam eventos, classificam crises, salvam resultados, notificam pessoas e analisam distribuição de recursos.
                  </p>
                </div>
                <span className="text-[10px] sm:text-[11px] text-[#525252] uppercase tracking-[0.18em] sm:tracking-[0.28em] font-bold">Python Tools</span>
              </div>

              <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-px bg-[#262626] border border-[#262626]">
                {[
                  { name: "fetch_usgs.py", desc: "Busca terremotos em tempo real na API do USGS e normaliza eventos por magnitude mínima." },
                  { name: "fetch_gdacs.py", desc: "Consome o feed RSS do GDACS para enchentes, ciclones e outros desastres naturais." },
                  { name: "fetch_eonet.py", desc: "Busca eventos NASA EONET, incluindo incêndios florestais, tempestades severas, vulcões e secas." },
                  { name: "fetch_conflict_data.py", desc: "Coleta conflitos armados e violência a partir de fontes como GDELT, UCDP e ACLED." },
                  { name: "classify_crisis.py", desc: "Usa Granite via watsonx.ai para determinar tipo e severidade do evento." },
                  { name: "save_classification.py", desc: "Atualiza ou insere o resultado da classificação no banco SQLite." },
                  { name: "match_volunteers.py", desc: "Calcula score de matching com embeddings semânticos e distância geográfica haversine." },
                  { name: "notify_telegram.py", desc: "Envia mensagens via Telegram para inscritos de um país ou região." },
                  { name: "notify_whatsapp.py", desc: "Notifica voluntários e ONGs cadastrados via WhatsApp." },
                  { name: "analyze_distribution.py", desc: "Identifica desequilíbrios na distribuição de voluntários entre crises ativas." },
                  { name: "suggest_reallocation.py", desc: "Gera sugestões concretas de realocação baseadas na distribuição atual." },
                  { name: "predict_humanitarian_risk.py", desc: "Chama o Granite para prever risco humanitário dos próximos 30 dias com dados históricos." }
                ].map((tool, i) => (
                  <div key={i} data-reveal-item style={{ transitionDelay: `${140 + i * 24}ms` }} className="tool-card bg-[#0a0a0a] p-5 sm:p-6 md:p-7">
                    <h4 className="text-blue-500 font-mono text-[11px] sm:text-[12px] mb-4 break-words">{tool.name}</h4>
                    <p className="text-sm text-[#a8a8a8] leading-relaxed font-light">{tool.desc}</p>
                  </div>
                ))}
              </div>
            </div>

            <div data-reveal-item>
              <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-5 sm:gap-6 mb-8 sm:mb-10">
                <div>
                  <h3 className="text-2xl min-[390px]:text-3xl md:text-4xl font-light text-white mb-4">Telas e fluxos</h3>
                  <p className="text-[#a8a8a8] text-sm sm:text-base leading-relaxed max-w-3xl">
                    A experiência separa perfis de admin, voluntário e ONG para que cada usuário veja apenas as ações úteis para responder, apoiar ou coordenar.
                  </p>
                </div>
                <span className="text-[10px] sm:text-[11px] text-[#525252] uppercase tracking-[0.18em] sm:tracking-[0.28em] font-bold">Web + Bot</span>
              </div>

              <div className="grid lg:grid-cols-2 border-t border-[#262626]">
                {[
                  { screen: "Login / Register", desc: "Autenticação com dot grid animado e cadastro por papel: voluntário, ONG ou admin." },
                  { screen: "Mapa Admin", desc: "Mapa fullscreen Leaflet com eventos globais, filtros, sidebar, popups e ingestão manual de dados." },
                  { screen: "Mapa Voluntário", desc: "Mapa com botão Quero Ajudar, associando o voluntário à crise selecionada." },
                  { screen: "Perfil Voluntário", desc: "Perfil, chat com volunteer_agent, crises próximas e missões inscritas em uma visão de decisão rápida." },
                  { screen: "Mapa ONG", desc: "Mapa com Apoiar Campanha, criando campanha pendente e vínculo da ONG com a crise." },
                  { screen: "Dashboard ONG", desc: "Métricas, gráficos Chart.js e cards de campanhas com status, urgência e detalhes." },
                  { screen: "Nova Campanha", desc: "Formulário para campanha vinculada a uma crise com habilidades, urgência e número de voluntários." },
                  { screen: "Detalhe da Campanha", desc: "Dados completos, chat com assistant_agent e lista de voluntários inscritos." },
                  { screen: "Minhas Campanhas", desc: "Campanhas filtradas por compatibilidade de habilidades e badge de notificações relevantes." },
                  { screen: "Bot Telegram", desc: "Comandos /crises, /meusdados, /inscrever e chat livre com o crisis_orchestrator." }
                ].map((item, i) => (
                  <div key={i} data-reveal-item style={{ transitionDelay: `${120 + i * 28}ms` }} className="screen-row grid sm:grid-cols-[160px_1fr] md:grid-cols-[180px_1fr] gap-3 sm:gap-4 p-5 sm:p-6 md:p-7 border-b lg:odd:border-r border-[#262626]">
                    <h4 className="text-white font-bold uppercase tracking-[0.12em] sm:tracking-[0.16em] text-[11px] sm:text-[12px] leading-relaxed">{item.screen}</h4>
                    <p className="text-sm text-[#a8a8a8] leading-relaxed font-light">{item.desc}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Process Flow */}
      <section data-reveal id="how-it-works" className="scroll-mt-14 py-24 md:py-40 px-5 md:px-12 bg-[#0a0a0a]">
        <div className="max-w-[1584px] mx-auto">
          <div className="grid lg:grid-cols-2 gap-16 lg:gap-32 items-center">
            <div className="space-y-12 md:space-y-16">
              <h2 className="text-4xl sm:text-5xl md:text-6xl font-light text-white leading-[1.14]">O ciclo de <br /> <span className="text-blue-500">coordenação digital.</span></h2>
              <div className="space-y-12 md:space-y-16">
                {[
                  { step: "Identificação", title: "Monitoramento e Ingestão", desc: "A plataforma analisa fluxos de dados de múltiplas fontes para detectar anomalias e riscos emergentes." },
                  { step: "Planejamento", title: "Mapeamento Contextual", desc: "Identificamos voluntários cujas habilidades e localização geográfica atendem precisamente à demanda identificada." },
                  { step: "Ação", title: "Convocação Orquestrada", desc: "Notificações são processadas via agentes digitais, permitindo o acompanhamento da resposta em tempo real." }
                ].map((item, i) => (
                  <div key={i} className="flex flex-col sm:flex-row gap-4 sm:gap-10 group">
                    <div className="text-blue-600 font-mono font-bold text-[11px] mt-1.5 uppercase whitespace-nowrap tracking-[0.22em] sm:tracking-[0.3em]">{item.step}</div>
                    <div className="space-y-3">
                      <h4 className="text-lg sm:text-xl font-bold text-white uppercase tracking-wide">{item.title}</h4>
                      <p className="text-base text-[#a8a8a8] leading-relaxed font-light">{item.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="relative aspect-[4/5] sm:aspect-square lg:aspect-square bg-[#161616] border border-[#262626] flex items-center justify-center overflow-hidden">
               <div className="absolute inset-0 opacity-[0.05] bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:40px_40px]"></div>
               <div className="relative z-10 w-full h-full flex items-center justify-center p-6 sm:p-10 md:p-12">
                  <div className="w-full h-full border border-white/5 flex flex-col">
                    <div className="h-10 border-b border-white/5 flex items-center px-4 gap-2">
                       <div className="w-2 h-2 rounded-full bg-red-500/50"></div>
                       <div className="w-2 h-2 rounded-full bg-yellow-500/50"></div>
                       <div className="w-2 h-2 rounded-full bg-green-500/50"></div>
                    </div>
                    <div className="flex-1 p-8 flex flex-col justify-center items-center text-center">
                       <Activity className="text-blue-500 mb-6 opacity-50" size={64} />
                       <span className="text-[9px] sm:text-[10px] font-mono text-[#525252] uppercase tracking-[0.28em] sm:tracking-[0.5em] leading-relaxed">Dashboard Operacional Crisis</span>
                    </div>
                  </div>
               </div>
            </div>
          </div>
        </div>
      </section>

      {/* Governance Section */}
      <section data-reveal id="governance" className="scroll-mt-14 py-24 md:py-36 px-5 md:px-12 bg-[#161616] border-y border-[#262626]">
        <div className="max-w-[1584px] mx-auto">
          <div className="grid lg:grid-cols-12 gap-10 md:gap-20 mb-14 md:mb-24">
            <div className="lg:col-span-5">
              <h2 className="text-[11px] font-bold text-blue-500 uppercase tracking-[0.28em] sm:tracking-[0.5em] mb-6">Governança</h2>
              <h3 className="text-4xl sm:text-5xl md:text-6xl font-light text-white leading-[1.14] md:leading-[1.12]">
                Confiança antes da <br />
                <span className="text-blue-500 italic">mobilização.</span>
              </h3>
            </div>
            <div className="lg:col-span-7 flex items-end">
              <p className="text-lg sm:text-xl md:text-2xl text-[#a8a8a8] font-light leading-relaxed max-w-4xl">
                Antes de qualquer chamada para campo, a Crisis organiza quem pode acessar, quais dados são necessários e como cada resposta será confirmada. A governança funciona como uma camada de coordenação para proteger voluntários, instituições e comunidades atendidas.
              </p>
            </div>
          </div>

          <div className="grid lg:grid-cols-3 border-t border-[#262626]">
            <div id="privacy" className="scroll-mt-14 p-8 md:p-12 border-b lg:border-b-0 lg:border-r border-[#262626]">
              <Database size={28} className="text-blue-500 mb-7 md:mb-10" />
              <span className="block text-[10px] font-bold text-[#525252] uppercase tracking-[0.24em] sm:tracking-[0.35em] mb-4">Dados essenciais</span>
              <h4 className="text-xl sm:text-2xl font-light text-white mb-6 leading-snug">Privacidade com propósito operacional.</h4>
              <p className="text-base text-[#a8a8a8] leading-relaxed font-light">
                O cadastro coleta apenas informações úteis para coordenação: identificação, contato, localização e competência técnica. Cada dado precisa justificar uma decisão de mobilização, priorização ou segurança.
              </p>
            </div>

            <div id="security" className="scroll-mt-14 p-8 md:p-12 border-b lg:border-b-0 lg:border-r border-[#262626]">
              <Shield size={28} className="text-blue-500 mb-7 md:mb-10" />
              <span className="block text-[10px] font-bold text-[#525252] uppercase tracking-[0.24em] sm:tracking-[0.35em] mb-4">Acesso controlado</span>
              <h4 className="text-xl sm:text-2xl font-light text-white mb-6 leading-snug">Segurança para operar sob pressão.</h4>
              <p className="text-base text-[#a8a8a8] leading-relaxed font-light">
                Fluxos institucionais ajudam a separar consulta, convocação e confirmação de disponibilidade, reduzindo exposição indevida de informações sensíveis durante eventos críticos.
              </p>
            </div>

            <div className="p-8 md:p-12">
              <Activity size={28} className="text-blue-500 mb-7 md:mb-10" />
              <span className="block text-[10px] font-bold text-[#525252] uppercase tracking-[0.24em] sm:tracking-[0.35em] mb-4">Rastreabilidade</span>
              <h4 className="text-xl sm:text-2xl font-light text-white mb-6 leading-snug">Decisões registradas do alerta à resposta.</h4>
              <p className="text-base text-[#a8a8a8] leading-relaxed font-light">
                A plataforma estrutura um histórico de solicitações, confirmações e encaminhamentos para que equipes possam auditar a operação e ajustar protocolos após cada ocorrência.
              </p>
            </div>
          </div>

          <div className="grid md:grid-cols-4 border-t border-[#262626]">
            {[
              { label: "Minimização", desc: "Dados limitados ao que acelera a resposta." },
              { label: "Consentimento", desc: "Participação clara para voluntários e instituições." },
              { label: "Responsabilidade", desc: "Papéis institucionais definidos antes da ação." },
              { label: "Continuidade", desc: "Registros úteis para melhoria de protocolos." }
            ].map((item, i) => (
              <div key={i} className="p-7 md:p-8 border-b md:border-b-0 md:border-r last:border-r-0 border-[#262626]">
                <span className="block text-blue-500 font-mono text-[11px] mb-5">0{i + 1}</span>
                <h5 className="text-white font-bold uppercase tracking-[0.16em] sm:tracking-[0.2em] text-[12px] mb-4">{item.label}</h5>
                <p className="text-sm text-[#a8a8a8] leading-relaxed font-light">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Registration Section */}
      <section data-reveal id="registration-form" className="scroll-mt-14 py-24 md:py-40 px-5 md:px-12 bg-[#161616]">
        <div className="max-w-[1584px] mx-auto grid lg:grid-cols-12 gap-14 lg:gap-24">
          <div className="lg:col-span-5 flex flex-col justify-center">
            <h2 className="text-4xl sm:text-5xl md:text-6xl font-light text-white mb-8 md:mb-10 leading-[1.16]">Participe da <br /> <span className="text-blue-500 font-normal italic">Rede Crisis</span></h2>
            <p className="text-[#a8a8a8] text-lg sm:text-xl font-light mb-10 md:mb-16 max-w-sm leading-relaxed">
              Sua integração na rede garante que a ajuda humanitária seja direcionada com base em dados de competência e logística.
            </p>
            
            <div className="space-y-4 md:space-y-6">
              <button 
                onClick={() => setFormType('volunteer')}
                className={`w-full text-left p-6 md:p-8 flex justify-between items-center gap-4 transition-all border-l-4 ${formType === 'volunteer' ? 'bg-[#262626] border-blue-600 text-white' : 'border-transparent text-[#525252] hover:text-[#a8a8a8]'}`}
              >
                <span className="text-sm sm:text-base md:text-lg font-bold uppercase tracking-[0.16em] sm:tracking-[0.2em]">Cadastro Voluntário</span>
                <ChevronRight size={20} className={formType === 'volunteer' ? 'text-blue-500' : 'opacity-0'} />
              </button>
              <button 
                onClick={() => setFormType('ngo')}
                className={`w-full text-left p-6 md:p-8 flex justify-between items-center gap-4 transition-all border-l-4 ${formType === 'ngo' ? 'bg-[#262626] border-blue-600 text-white' : 'border-transparent text-[#525252] hover:text-[#a8a8a8]'}`}
              >
                <span className="text-sm sm:text-base md:text-lg font-bold uppercase tracking-[0.16em] sm:tracking-[0.2em]">Acesso Institucional</span>
                <ChevronRight size={20} className={formType === 'ngo' ? 'text-blue-500' : 'opacity-0'} />
              </button>
            </div>
          </div>

          <div className="lg:col-span-7">
            <div className="bg-[#0a0a0a] p-6 sm:p-10 md:p-20 border border-[#262626]">
              <form className="grid md:grid-cols-2 gap-x-10 lg:gap-x-16 gap-y-9 md:gap-y-12" onSubmit={handleRegistrationSubmit}>
                <div className="space-y-4 group border-b border-[#262626] focus-within:border-blue-500 transition-all">
                  <label className="block text-[10px] sm:text-[11px] font-bold text-[#525252] uppercase tracking-[0.22em] sm:tracking-[0.3em]">Identificação</label>
                  <input type="text" className="w-full bg-transparent py-4 outline-none text-white text-base sm:text-lg placeholder:text-[#262626]" placeholder={formType === 'volunteer' ? "Nome Completo" : "Razão Social"} />
                </div>
                <div className="space-y-4 group border-b border-[#262626] focus-within:border-blue-500 transition-all">
                  <label className="block text-[10px] sm:text-[11px] font-bold text-[#525252] uppercase tracking-[0.22em] sm:tracking-[0.3em]">Comunicação</label>
                  <input type="tel" className="w-full bg-transparent py-4 outline-none text-white text-base sm:text-lg placeholder:text-[#262626]" placeholder="E-mail ou WhatsApp" />
                </div>
                <div className="space-y-4 group border-b border-[#262626] focus-within:border-blue-500 transition-all">
                  <label className="block text-[10px] sm:text-[11px] font-bold text-[#525252] uppercase tracking-[0.22em] sm:tracking-[0.3em]">Geografia</label>
                  <input type="text" className="w-full bg-transparent py-4 outline-none text-white text-base sm:text-lg placeholder:text-[#262626]" placeholder="Cidade / UF" />
                </div>
                <div className="space-y-4 group border-b border-[#262626] focus-within:border-blue-500 transition-all">
                  <label className="block text-[10px] sm:text-[11px] font-bold text-[#525252] uppercase tracking-[0.22em] sm:tracking-[0.3em]">Domínio Técnico</label>
                  <select className="w-full bg-transparent py-4 outline-none text-white text-base sm:text-lg appearance-none cursor-pointer">
                    <option className="bg-[#0a0a0a]">Médico / Saúde</option>
                    <option className="bg-[#0a0a0a]">Resgate e Campo</option>
                    <option className="bg-[#0a0a0a]">Logística de Suporte</option>
                    <option className="bg-[#0a0a0a]">Arquitetura de Dados</option>
                  </select>
                </div>
                
                <div className="md:col-span-2 pt-8 md:pt-16">
                  <button type="submit" className="w-full bg-white text-black py-5 sm:py-7 flex items-center justify-between gap-6 px-6 sm:px-12 hover:bg-blue-600 hover:text-white transition-all transform active:scale-[0.99]">
                    <span className="text-sm sm:text-base font-bold uppercase tracking-[0.18em] sm:tracking-[0.3em]">Solicitar Ingresso</span>
                    <ArrowRight size={28} />
                  </button>
                  <div className="mt-10 flex items-center gap-4 text-[#525252]">
                    <Shield size={18} />
                    <span className="text-[10px] sm:text-[11px] font-medium uppercase tracking-[0.14em] sm:tracking-[0.2em] leading-relaxed">Conformidade com os protocolos de segurança e LGPD IBM</span>
                  </div>
                </div>
              </form>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer data-reveal className="py-20 md:py-32 px-5 md:px-12 border-t border-[#262626]">
        <div className="max-w-[1584px] mx-auto flex flex-col lg:flex-row justify-between items-start gap-14 lg:gap-24">
          <div className="space-y-8 md:space-y-10">
            <span className="text-2xl font-bold tracking-tighter text-white uppercase">
               Crisis
            </span>
            <p className="max-w-xs text-[#a8a8a8] font-light leading-relaxed text-base italic">
              A inteligência agêntica a serviço da resiliência social e resposta humanitária estruturada.
            </p>
          </div>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-16 lg:gap-x-32 gap-y-12 md:gap-y-16 w-full lg:w-auto">
            <div className="space-y-8">
              <h5 className="text-white font-bold uppercase text-[11px] tracking-[0.28em] sm:tracking-[0.4em]">Plataforma</h5>
              <div className="flex flex-col gap-4 text-[13px] text-[#525252]">
                <button onClick={() => scrollToSection('mission')} className="hover:text-blue-500 text-left transition-colors uppercase tracking-widest">Missão</button>
                <button onClick={() => scrollToSection('technology')} className="hover:text-blue-500 text-left transition-colors uppercase tracking-widest">Tecnologia</button>
                <button onClick={() => scrollToSection('how-it-works')} className="hover:text-blue-500 text-left transition-colors uppercase tracking-widest">Processos</button>
                <button onClick={() => scrollToSection('registration-form')} className="hover:text-blue-500 text-left transition-colors uppercase tracking-widest">Cadastro</button>
              </div>
            </div>
            <div className="space-y-8">
              <h5 className="text-white font-bold uppercase text-[11px] tracking-[0.28em] sm:tracking-[0.4em]">Governança</h5>
              <div className="flex flex-col gap-4 text-[13px] text-[#525252]">
                <button onClick={() => scrollToSection('privacy')} className="hover:text-blue-500 text-left transition-colors uppercase tracking-widest">Privacidade</button>
                <button onClick={() => scrollToSection('security')} className="hover:text-blue-500 text-left transition-colors uppercase tracking-widest">Segurança</button>
              </div>
            </div>
          </div>
        </div>
        <div className="max-w-[1584px] mx-auto mt-20 md:mt-40 pt-10 border-t border-[#262626] text-center text-[10px] sm:text-[11px] uppercase font-bold tracking-[0.2em] sm:tracking-[0.4em] text-[#393939] leading-relaxed">
          © 2026 Crisis Hub
        </div>
      </footer>
    </div>
  );
};

export default App;

