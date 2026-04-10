import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Routes } from '@angular/router';
import { NgChartsModule } from 'ng2-charts';
import { InsightsComponent } from './insights.component';

const routes: Routes = [
  { path: '', component: InsightsComponent }
];

@NgModule({
  declarations: [InsightsComponent],
  imports: [
    CommonModule,
    NgChartsModule,
    RouterModule.forChild(routes),
  ]
})
export class InsightsModule {}
