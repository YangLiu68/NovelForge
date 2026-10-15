import { Link, Route, Routes } from "react-router-dom";

import ChapterView from "./pages/ChapterView";
import Characters from "./pages/Characters";
import Contradictions from "./pages/Contradictions";
import Facts from "./pages/Facts";
import NovelList from "./pages/NovelList";
import Overview from "./pages/Overview";
import Search from "./pages/Search";
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
          <Route path="facts" element={<Facts />} />
        </Route>
        <Route path="*" element={<p className="page">Not found. <Link to="/">Home</Link></p>} />
      </Routes>
    </div>
  );
}
