import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';

import { BoardComponent } from './board/board.component';
import { IssueDetailComponent } from './issues/issue-detail/issue-detail.component';
import { IssueListComponent } from './issues/issue-list/issue-list.component';
import { SettingsComponent } from './settings/settings.component';
import { TeamComponent } from './team/team.component';

const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'issues' },
  { path: 'issues', component: IssueListComponent, title: 'Issues' },
  { path: 'issues/:id', component: IssueDetailComponent, title: 'Issue' },
  { path: 'board', component: BoardComponent, title: 'Board' },
  { path: 'team', component: TeamComponent, title: 'Team' },
  { path: 'settings', component: SettingsComponent, title: 'Settings' },
  { path: '**', redirectTo: 'issues' },
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule],
})
export class AppRoutingModule {}
