import { Link, Route, Routes } from "react-router-dom";

import CanonPage from "./pages/CanonPage";
import ChapterView from "./pages/ChapterView";
import Characters from "./pages/Characters";
import Contradictions from "./pages/Contradictions";
import DraftAssistant from "./pages/DraftAssistant";
import Facts from "./pages/Facts";
import GraphPage from "./pages/GraphPage";
import NovelList from "./pages/NovelList";
import Overview from "./pages/Overview";
import Review from "./pages/Review";
import Search from "./pages/Search";
import StoryPage from "./pages/StoryPage";
import Workspace from "./pages/Workspace";

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          NovelForge
        </Link>
        <span className="tagline">evidence-grounded fiction workspace</span>
      </header>
      <Routes>
        <Route path="/" element={<NovelList />} />
        <Route path="/novels/:novelId" element={<Workspace />}>
          <Route index element={<Overview />} />
          <Route path="chapters/:chapterId" element={<ChapterView />} />
          <Route path="characters" element={<Characters />} />
          <Route path="search" element={<Search />} />
          <Route path="contradictions" element={<Contradictions />} />
          <Route path="story" element={<StoryPage />} />
          <Route path="facts" element={<Facts />} />
          <Route path="review" element={<Review />} />
          <Route path="canon" element={<CanonPage />} />
          <Route path="draft" element={<DraftAssistant />} />
          <Route path="graph" element={<GraphPage />} />
        </Route>
        <Route path="*" element={<p className="page">Not found. <Link to="/">Home</Link></p>} />
      </Routes>
    </div>
  );
}
